"""User-driven vanilla console diagnostics. Never calls GECK or executes game commands."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .transport import BridgeError


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Probe(Strict):
    key: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
    kind: Literal['quest_variable', 'item_count', 'disabled', 'dead']
    local_form: str = Field(pattern=r'^[0-9A-Fa-f]{6}$')
    variable: str | None = Field(default=None, pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')

    @model_validator(mode='after')
    def variable_scope(self):
        if (self.kind == 'quest_variable') != (self.variable is not None):
            raise ValueError('Only quest_variable requires a variable')
        return self


class Rule(Strict):
    key: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
    kind: Literal['equals', 'range', 'count_limit', 'unchanged', 'mutually_exclusive']
    fields: list[str] = Field(min_length=1, max_length=100)
    value: float | None = Field(default=None, allow_inf_nan=False)
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode='after')
    def operands(self):
        if len(set(self.fields)) != len(self.fields):
            raise ValueError('Duplicate rule field')
        if self.kind == 'equals' and self.value is None:
            raise ValueError('equals requires value')
        if self.kind == 'range' and self.minimum is None and self.maximum is None:
            raise ValueError('range requires minimum or maximum')
        if self.kind == 'count_limit' and (self.maximum is None or self.maximum < 0):
            raise ValueError('count_limit requires nonnegative maximum')
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError('minimum exceeds maximum')
        return self


class Profile(Strict):
    schema_version: Literal[1] = 1
    plugin: str = Field(pattern=r'^[A-Za-z0-9_][A-Za-z0-9_. -]{0,120}\.(?:esp|esm)$')
    probes: list[Probe] = Field(min_length=1, max_length=100)
    rules: list[Rule] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def unique_keys(self):
        if '..' in self.plugin:
            raise ValueError('Invalid plugin filename')
        keys = {p.key for p in self.probes}
        if len(keys) != len(self.probes) or len({r.key for r in self.rules}) != len(self.rules):
            raise ValueError('Duplicate probe/rule key')
        if any(set(r.fields) - keys for r in self.rules):
            raise ValueError('Rule references unknown probe')
        return self


class Mapping(Strict):
    prefix: str = Field(pattern=r'^[0-9A-Fa-f]{2}$')
    source: Literal['unknown', 'disk_order', 'user_runtime_observation'] = 'unknown'
    evidence: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def proof(self):
        if self.prefix.upper() == 'FF':
            raise ValueError('Dynamic forms are unsupported')
        if self.source == 'user_runtime_observation' and len(self.evidence.strip()) < 12:
            raise ValueError('Describe fresh runtime evidence for this save/session')
        return self


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, obj):
    # Atomic replacement prevents a collector interruption leaving half a manifest.
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError('An explicit save/checkpoint label (1..200 characters) is required')
    return value


def plan(profile, mapping, token):
    """Compile an allowlisted flattened program; raw console commands are never accepted."""
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', token):
        raise ValueError('Batch/log token must be a simple ASCII filename stem')
    commands = []
    targets = []
    for probe in profile.probes:
        form = mapping.prefix.upper() + probe.local_form.upper()
        if probe.kind == 'quest_variable':
            command = 'sqv ' + form
        elif probe.kind == 'item_count':
            command = 'player.GetItemCount ' + form
        else:
            commands.append('prid ' + form)
            command = 'GetDisabled' if probe.kind == 'disabled' else 'GetDead'
        commands.append(command)
        targets.append({'probe': probe.model_dump(), 'command_index': len(commands) - 1})
    commands.append('prid 00000014')
    return {'commands': commands, 'targets': targets,
            'log_name': token + '.log',
            'batches': {token + '_start.txt': [f'scof "{token}.log"', *commands],
                        token + '_sample.txt': commands},
            'side_effects': ['SCOF redirects console logging; run start only once.',
                             'PRID changes selected reference; final selection is player (00000014).',
                             'Close stops bridge collection only. Quit FNV normally to stop SCOF.',
                             'Snapshots are sequential, not atomic or same-frame mutation verification.']}


NUMBER = r'(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)'
ERROR = re.compile(r'\berror\b|\binvalid\b|\bnot found\b|\bunknown command\b|\bcould not\b|\bfailed\b|\bmissing parameter\b|\bscript command\b', re.I)


def norm(command):
    return ' '.join(command.split()).casefold()


def parse(text, program, state=None):
    """Strict echoed-command sequence binds observations to requested forms and selection.

    Only newline-terminated lines are considered. An unrelated command invalidates an
    in-progress snapshot. The final player selection echo seals the preceding output.
    """
    commands = program['commands']
    targets = {t['command_index']: t['probe'] for t in program['targets']}
    samples, unrelated, issues = [], [], []
    state = state or {}
    active = state.get('active')
    index = state.get('index', -1)
    line_count = state.get('line_count', 0)
    text = state.get('partial', '') + text
    # Console compiler errors can end with CR CR LF. splitlines() treats the
    # first CR as an unfinished line, dropping the rest of an already-read tail.
    # LF is the record boundary; all preceding CRs are harmless whitespace.
    complete_lines = text.split('\n')
    partial = complete_lines.pop()
    for number, body in enumerate(complete_lines, line_count + 1):
        raw = body + '\n'
        line_count = number
        line = raw.strip()
        echo = re.fullmatch(r'>\s*(.*)', line)
        provenance = {'line': number, 'raw': raw.rstrip('\r\n')}
        if echo:
            command = norm(echo[1])
            expected = index + 1
            if active is not None and expected < len(commands) and command == norm(commands[expected]):
                index = expected
            elif command == norm(commands[0]):
                if active is not None:
                    issues.append({'code': 'INCOMPLETE_SAMPLE', **provenance})
                active = {'values': {}, 'errors': [], 'start_line': number, 'invalid_fields': []}
                index = 0
            else:
                if active is not None:
                    issues.append({'code': 'UNEXPECTED_COMMAND', **provenance})
                active = None
                index = -1
            if active is not None and index == len(commands) - 1:
                active['end_line'] = number
                samples.append(active)
                active = None
            continue
        if ERROR.search(line):
            error = {'code': 'CONSOLE_ERROR', **provenance}
            (active['errors'] if active is not None else unrelated).append(error)
            continue
        if active is None or index not in targets:
            continue
        probe = targets[index]
        if probe['kind'] == 'quest_variable':
            match = re.fullmatch(r'->' + re.escape(probe['variable']) + r'\s*=\s*' + NUMBER, line, re.I)
        else:
            name = {'item_count': 'GetItemCount', 'dead': 'GetDead', 'disabled': 'GetDisabled'}[probe['kind']]
            match = re.fullmatch(name + r'\s*>>\s*' + NUMBER, line, re.I)
        if match:
            value = float(match[1])
            valid = math.isfinite(value)
            if probe['kind'] == 'item_count':
                valid = valid and value >= 0 and value.is_integer()
            if probe['kind'] in ('dead', 'disabled'):
                valid = valid and value in (0, 1)
            if not valid or probe['key'] in active['values'] or probe['key'] in active['invalid_fields']:
                active['errors'].append({'code': 'INVALID_OBSERVATION', **provenance})
                active['values'].pop(probe['key'], None)
                active['invalid_fields'].append(probe['key'])
            else:
                active['values'][probe['key']] = {'value': value, **provenance}
    return {'samples': samples, 'unrelated_errors': unrelated, 'issues': issues,
            'pending': active is not None or bool(partial),
            'state': {'active': active, 'index': index, 'line_count': line_count, 'partial': partial}}


def evaluate(profile, checkpoint, baseline, identity):
    values = checkpoint['values'] if checkpoint else {}
    before = baseline['values'] if baseline else {}
    results = []
    for rule in profile.rules:
        status = 'inconclusive'
        if (checkpoint and checkpoint['capture'] == 'complete' and identity == 'user_attested'
                and all(k in values for k in rule.fields)
                and (rule.kind != 'unchanged' or (baseline and baseline is not checkpoint and baseline['capture'] == 'complete'
                                                 and all(k in before for k in rule.fields)))):
            nums = [values[k]['value'] for k in rule.fields]
            if rule.kind == 'equals':
                passed = all(v == rule.value for v in nums)
            elif rule.kind in ('range', 'count_limit'):
                passed = all((rule.minimum is None or v >= rule.minimum) and
                             (rule.maximum is None or v <= rule.maximum) for v in nums)
            elif rule.kind == 'unchanged':
                passed = all(values[k]['value'] == before[k]['value'] for k in rule.fields)
            else:
                passed = sum(v != 0 for v in nums) <= 1
            status = 'pass' if passed else 'fail'
        results.append({'key': rule.key, 'status': status})
    return results


class Runtime:
    def __init__(self, project, on_change=lambda: None):
        self.project = project
        self.root = project.state_dir / 'runtime'
        self.on_change = on_change

    def load(self, session):
        if not re.fullmatch(r'[a-f0-9]{32}', session):
            raise ValueError('Invalid runtime_session')
        folder = self.root / session
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['project_id'] != self.project.project_id or manifest['game_root'] != str(self.project.game_root.resolve()):
            raise ValueError('Runtime session belongs to a different project/game installation')
        return folder, manifest

    def prepare(self, profile, save_label, runtime_mapping, expected_plugin_hash, preview=False):
        profile = Profile.model_validate(profile)
        mapping = Mapping.model_validate(runtime_mapping)
        label(save_label)
        if not re.fullmatch(r'[a-f0-9]{64}', expected_plugin_hash):
            raise ValueError('expected_plugin_hash must be SHA-256')
        plugin = self.project.game_root / 'Data' / profile.plugin
        if file_digest(plugin) != expected_plugin_hash:
            raise BridgeError('RUNTIME_PLUGIN_CHANGED', 'Installed plugin hash differs')
        session = uuid.uuid4().hex
        # Keep user-entered vanilla BAT commands short. Exclusive creation and the
        # preflight collision check still refuse to reuse any existing target.
        token = 'gd_' + session[:8]
        program = plan(profile, mapping, token)
        if preview:
            return {'preview': True, **program}
        if any((self.project.game_root / name).exists() for name in [program['log_name'], *program['batches']]):
            raise BridgeError('RUNTIME_FILE_EXISTS', 'Refusing to overwrite existing runtime files')
        self.on_change()
        folder = self.root / session
        folder.mkdir(parents=True)
        manifest = {'schema_version': 1, 'runtime_session': session, 'profile': profile.model_dump(),
                    'project_id': self.project.project_id, 'game_root': str(self.project.game_root.resolve()),
                    'save_label': save_label, 'mapping': mapping.model_dump(),
                    'identity': 'user_attested' if mapping.source == 'user_runtime_observation' else 'unverified',
                    'plugin_sha256': expected_plugin_hash, 'created': now(), 'closed': False,
                    'program': program, 'owned_files': {}, 'checkpoints': [], 'consumed_line': 0,
                    'cursor': 0, 'prefix_sha256': digest(b'')}
        save(folder / 'manifest.json', manifest)
        try:
            for filename, commands in program['batches'].items():
                path = self.project.game_root / filename
                data = ('\r\n'.join(commands) + '\r\n').encode('ascii')
                with path.open('xb') as stream:
                    stream.write(data)
                manifest['owned_files'][str(path.resolve())] = digest(data)
                save(folder / 'manifest.json', manifest)
        except OSError as error:
            raise BridgeError('RUNTIME_PREPARE_INTERRUPTED', 'Some helpers may exist; inspect the manifest and close/archive before retrying',
                              {'runtime_session': session, 'manifest': str(folder / 'manifest.json'),
                               'owned_files': manifest['owned_files']}) from error
        manifest['prepared'] = True
        save(folder / 'manifest.json', manifest)
        if file_digest(plugin) != expected_plugin_hash:
            raise BridgeError('RUNTIME_PLUGIN_CHANGED', 'Plugin changed during preparation; retain manifest for review',
                              {'runtime_session': session})
        return {'runtime_session': session, 'manifest': str(folder / 'manifest.json'),
                'identity': manifest['identity'], **program,
                'instructions': [f'Once only: bat {token}_start',
                                 f'After each gameplay checkpoint: bat {token}_sample',
                                 'Collect with a new explicit checkpoint_label before another snapshot.',
                                 'Any save/load or load-order change requires a NEW session and baseline.']}

    def collect(self, session, checkpoint_label):
        folder, manifest = self.load(session)
        label(checkpoint_label)
        if manifest['closed']:
            raise BridgeError('RUNTIME_CLOSED', 'Collection is closed')
        if not manifest.get('prepared'):
            raise BridgeError('RUNTIME_NOT_PREPARED', 'Interrupted preparation; inspect manifest-owned files before close/archive')
        if manifest.get('invalidated'):
            return manifest['invalidated']
        if any(c['label'] == checkpoint_label for c in manifest['checkpoints']):
            raise BridgeError('CHECKPOINT_EXISTS', 'Use report to replay, or a new checkpoint label')
        log = self.project.game_root / manifest['program']['log_name']
        if not log.exists():
            return {'status': 'awaiting_output', 'code': 'LOG_MISSING', 'next': 'Run the start batch once in FNV.'}
        # Bounded retries, total read bounded to 16 MiB. Confirm the consumed prefix to
        # detect truncation/replacement, including same-size rewrites after SCOF restart.
        for attempt in range(3):
            try:
                with log.open('rb') as stream:
                    prefix = stream.read(manifest['cursor'])
                    tail = stream.read(16 * 1024 * 1024 - len(prefix) + 1)
                break
            except OSError:
                if attempt == 2:
                    return {'status': 'awaiting_output', 'code': 'LOG_LOCKED', 'next': 'Retry collection after FNV flushes output.'}
                time.sleep(0.05)
        if len(prefix) != manifest['cursor'] or digest(prefix) != manifest['prefix_sha256']:
            result = {'status': 'error', 'code': 'LOG_REPLACED',
                    'next': 'Preserve evidence; prepare a new session and explicit baseline. Do not reuse this log.'}
            manifest['invalidated'] = result
            save(folder / 'manifest.json', manifest)
            return result
        if len(prefix) + len(tail) > 16 * 1024 * 1024:
            result = {'status': 'error', 'code': 'LOG_TOO_LARGE', 'next': 'Close collection and prepare a new session.'}
            manifest['invalidated'] = result
            save(folder / 'manifest.json', manifest)
            return result
        data = prefix + tail
        # Preserve raw local source for replay/provenance. Nothing is exported implicitly.
        (folder / 'console.log').write_bytes(data)
        # Only parse the newly appended tail. Keep the unfinished command/line state
        # across process restarts; the prefix is read solely to verify continuity.
        parsed = parse(tail.decode('cp1252', errors='replace'), manifest['program'], manifest.get('parser_state'))
        manifest['parser_state'] = parsed['state']
        manifest.setdefault('pending_samples', []).extend(parsed['samples'])
        manifest.setdefault('pending_issues', []).extend(parsed['issues'])
        manifest.setdefault('pending_errors', []).extend(parsed['unrelated_errors'])
        manifest['cursor'] = len(data)
        manifest['prefix_sha256'] = digest(data)
        save(folder / 'manifest.json', manifest)
        fresh = manifest['pending_samples']
        if not fresh:
            return {'status': 'awaiting_output', 'code': 'NO_FRESH_SAMPLE',
                    'pending': parsed['pending'], 'issues': manifest['pending_issues'],
                    'unrelated_errors': manifest['pending_errors'],
                    'next': 'Run the sample batch once, then retry after output is flushed.'}
        if len(fresh) != 1:
            result = {'status': 'error', 'code': 'AMBIGUOUS_CHECKPOINT',
                    'next': 'Multiple unlabelled samples; prepare a new session with explicit checkpoints.'}
            manifest['invalidated'] = result
            save(folder / 'manifest.json', manifest)
            return result
        sample = fresh[0]
        missing = [p['key'] for p in manifest['profile']['probes'] if p['key'] not in sample['values']]
        issues = [e for e in manifest['pending_issues'] if e['line'] <= sample['end_line']]
        checkpoint = {**sample, 'label': checkpoint_label, 'collected': now(), 'missing': missing,
                      'unrelated_errors': [e for e in manifest['pending_errors'] if e['line'] <= sample['end_line']],
                      'issues': issues, 'capture': 'errored' if sample['errors'] or issues else
                      'partial' if missing else 'complete'}
        manifest['checkpoints'].append(checkpoint)
        manifest['pending_samples'] = []
        manifest['pending_issues'] = [e for e in manifest['pending_issues'] if e['line'] > sample['end_line']]
        manifest['pending_errors'] = [e for e in manifest['pending_errors'] if e['line'] > sample['end_line']]
        manifest['consumed_line'] = sample['end_line']
        manifest['cursor'] = len(data)
        manifest['prefix_sha256'] = digest(data)
        save(folder / 'manifest.json', manifest)
        return self.report(session)

    def report(self, session, baseline_checkpoint=None, sanitized=False):
        folder, manifest = self.load(session)
        checkpoints = manifest['checkpoints']
        current = checkpoints[-1] if checkpoints else None
        baseline = checkpoints[0] if checkpoints else None
        if baseline_checkpoint is not None:
            baseline = next((c for c in checkpoints if c['label'] == baseline_checkpoint), None)
            if baseline is None:
                raise ValueError('Unknown baseline_checkpoint')
        identity = manifest['identity']
        if manifest.get('invalidated'):
            identity = 'continuity_invalid'
        plugin = self.project.game_root / 'Data' / manifest['profile']['plugin']
        try:
            if file_digest(plugin) != manifest['plugin_sha256']:
                identity = 'plugin_changed'
        except OSError:
            identity = 'plugin_unavailable'
        changes = {}
        if current and baseline:
            changes = {k: {'before': baseline['values'][k]['value'], 'after': v['value'],
                           'delta': v['value'] - baseline['values'][k]['value']}
                       for k, v in current['values'].items() if k in baseline['values']
                       and v['value'] != baseline['values'][k]['value']}
        rules = evaluate(Profile.model_validate(manifest['profile']), current, baseline, identity)
        result = {'runtime_session': session, 'identity': identity, 'closed': manifest['closed'],
                  'status': current['capture'] if current else 'awaiting_output',
                  'source': str(folder / 'console.log'),
                  'checkpoint': current, 'baseline_checkpoint': baseline['label'] if baseline else None,
                  'changes': changes, 'rules': rules,
                  'collection_error': manifest.get('invalidated'),
                  'assertions': 'inconclusive' if not rules or any(r['status'] == 'inconclusive' for r in rules)
                  else 'fail' if any(r['status'] == 'fail' for r in rules) else 'pass',
                  'limits': manifest['program']['side_effects'],
                  'next': 'Inspect missing/errors; no gameplay pass is implied by capture success.'}
        if sanitized:
            # Explicit allowlist: no labels, mapping evidence, paths or raw player output.
            result = {k: result[k] for k in ('identity', 'status', 'assertions', 'changes', 'rules', 'limits')}
            save(folder / 'report-sanitized.json', result)
            return result
        save(folder / 'report.json', result)
        lines = ['# Runtime diagnostics', '', f'Identity: {identity}', f'Capture: {result["status"]}',
                 f'Assertions: {result["assertions"]}',
                 'Checkpoint: ' + (current['label'] if current else '(none)'),
                 'Baseline: ' + (result['baseline_checkpoint'] or '(none)'), '',
                 '| Probe | Value | Source line |', '| --- | --- | --- |']
        if current:
            lines += [f'| {key} | {value["value"]} | {value["line"]} |'
                      for key, value in current['values'].items()]
            lines += ['', 'Missing: ' + (', '.join(current['missing']) or 'none')]
        lines += ['', 'Changes: ' + json.dumps(changes), '', 'Rules:']
        lines += [f'- {r["key"]}: {r["status"]}' for r in rules] or ['- None; inconclusive.']
        lines += ['', 'Errors:']
        errors = (current['errors'] + current['issues'] + current['unrelated_errors']) if current else []
        lines += [f'- Line {e["line"]}: {e["code"]}: {e["raw"]}' for e in errors] or ['- None in this checkpoint.']
        if result['collection_error']:
            lines += [json.dumps(result['collection_error'])]
        lines += ['', result['next'], '', *result['limits']]
        (folder / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return result

    def close(self, session, archive_helpers=False, game_exited=False):
        folder, manifest = self.load(session)
        if archive_helpers and not game_exited:
            raise ValueError('Archival requires explicit game_exited=true after normal FNV exit')
        self.on_change()
        manifest['closed'] = True
        manifest['closed_at'] = manifest.get('closed_at', now())
        manifest.setdefault('archived', [])
        preserved = []
        if archive_helpers:
            archive = folder / 'archived'
            archive.mkdir(exist_ok=True)
            for owned, expected in manifest['owned_files'].items():
                path = Path(owned)
                if path.parent.resolve() != self.project.game_root.resolve() or path.name not in manifest['program']['batches']:
                    raise ValueError('Invalid owned helper path')
                if path.is_symlink() or (path.exists() and digest(path.read_bytes()) != expected):
                    preserved.append(str(path))
                elif path.exists():
                    destination = archive / path.name
                    if destination.exists():
                        preserved.append(str(path))
                    else:
                        path.rename(destination)
                        manifest['archived'].append(str(path))
        save(folder / 'manifest.json', manifest)
        return {**self.report(session), 'archived': manifest['archived'], 'preserved': preserved,
                'logger_stopped': False, 'next': 'Collection closed. Only normal FNV exit is verified to stop SCOF.'}
