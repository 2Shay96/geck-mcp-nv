"""Bounded, journal-backed compile checkpoints shared by CLI and MCP.

One resume performs at most one UI phase. Dispatch intent is durable BEFORE
calling Win32. A pending operation reserves the existing editor lock namespace.
No quiet interval is proof, and no uncertain Save is automatically replayed.
"""
from contextlib import closing
import hashlib
import json
import re
import time

from bridge_lock import reservation
from .authoring import Authoring, atomic_write, sha
from .esp import codec, generic, scripts
from .transport import BridgeError


PHASES = ('editor_opening', 'selecting_script', 'source_verified', 'save_requested', 'busy_dialog_review', 'editor_close_requested',
          'editor_closed', 'plugin_save_requested', 'persisted_script_verified',
          'cached', 'rebuilt', 'installed')


def source_hash(text):
    return hashlib.sha256(scripts.normalized(text).decode('cp1252').encode('utf-8')).hexdigest()


def script_order(spec, base, pending):
    """Compile declared quest-variable dependencies first; refuse cycles instead of guessing."""
    aliases = {name.casefold(): name for name in pending}
    for edid, rec in spec.get('records', {}).items():
        if rec.get('type') == 'QUST':
            for field in rec.get('fields', []):
                target = field.get('form', '')
                if field.get('tag') == 'SCRI' and target.startswith('@') and target[1:] in pending:
                    aliases[edid.casefold()] = target[1:]
    dependencies = {}
    for edid in pending:
        text = generic.script_text(base, spec['records'][edid], edid, edid).decode('cp1252')
        code = '\n'.join(line.split(';', 1)[0] for line in text.splitlines())
        dependencies[edid] = {aliases[name.casefold()] for name in re.findall(r'\b([A-Za-z_]\w*)\s*\.', code)
                              if name.casefold() in aliases and aliases[name.casefold()] != edid}
    order = []
    while dependencies:
        ready = sorted((edid for edid, deps in dependencies.items() if not deps),
                       key=lambda e: (spec['records'][e].get('script_type') != 'quest', e))
        if not ready:
            raise ValueError('Cyclic script dependencies require a reviewed bootstrap compile: ' + ', '.join(sorted(dependencies)))
        order.extend(ready)
        for edid in ready:
            del dependencies[edid]
        for deps in dependencies.values():
            deps.difference_update(ready)
    return order


class Compilation:
    def __init__(self, service):
        self.s = service
        self.p = service.project
        self.auth = Authoring(self.p)
        with closing(service.db()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS compile_checkpoints (id TEXT PRIMARY KEY, data TEXT NOT NULL)')

    def read(self, operation_id):
        with closing(self.s.db()) as db:
            row = db.execute('SELECT data FROM compile_checkpoints WHERE id=?', (operation_id,)).fetchone()
        if row is None:
            raise ValueError('No compile checkpoint in this project')
        return json.loads(row[0])

    def write(self, cp, phase=None):
        if phase:
            cp['phase'] = phase
        cp['updatedAt'] = time.time()
        with closing(self.s.db()) as db, db:
            db.execute('INSERT OR REPLACE INTO compile_checkpoints VALUES (?,?)', (cp['operationId'], json.dumps(cp)))

    def owner(self, op):
        return {'operationId': op, 'journal': str(self.s.db_path.resolve())}

    def result(self, cp, outcome='pending', message=None):
        return {**cp, '_outcome': outcome, 'compiled': outcome == 'verified',
                'elapsedSeconds': round(time.time() - cp['startedAt'], 3),
                'next': message or 'Call geck_compile_resume with this operationId; do not start another compile.'}

    def start(self, request_key, deadline_seconds=1200):
        def action():
            spec = self.auth.load_spec()
            receipt = self.auth.receipt()
            state = self.s.check_session()
            installed = self.p.plugin_path.read_bytes()
            expected = sha(installed)
            if receipt['sha256'] != expected or self.s.loaded_plugin(state['sessionId']) != expected:
                raise BridgeError('LOAD_REQUIRED', 'Build/install/load these exact bytes through the bridge first',
                                  {'installedSha256': expected, 'builtSha256': receipt['sha256'],
                                   'loadedSha256': self.s.loaded_plugin(state['sessionId'])})
            if state['unsavedChanges']:
                raise BridgeError('UNSAVED_CHANGES', 'Resolve existing user edits before starting compile')
            # Rebuild dry-run detects moved sources/FormIDs/cache before any UI dispatch.
            fresh, _ = self.auth.build()
            if fresh['sha256'] != receipt['sha256']:
                raise BridgeError('STALE_BUILD', 'Sources/dependencies changed; rebuild/install/reload first')
            pending = receipt['uncompiledScripts']
            cp = {'operationId': self.s._active_operation, 'sessionId': state['sessionId'],
                  'startedAt': time.time(), 'deadlineAt': time.time() + deadline_seconds,
                  'context': self.auth.compile_context(spec), 'formIds': receipt['formIds'],
                  'expectedDiskSha256': expected, 'loadedSha256': expected,
                  'specSha256': receipt['specSha256'], 'scripts': {}, 'index': 0,
                  'intendedAssets': receipt.get('assets'),
                  'order': script_order(spec, self.auth.spec_path.parent, pending),
                  'loadVerification': 'independent of persisted compile verification'}
            # The uncompiled input must actually contain no old bytecode: prevents laundering old SCDA.
            found = generic.extract_compiled(codec.parse(installed))
            if any(found.get(e, {}).get('compiledSize', 0) for e in pending):
                raise BridgeError('STALE_BYTECODE', 'Pending script already has bytecode; rebuild an uncompiled input')
            reservation(self.p.lock_root, self.owner(cp['operationId']))
            self.write(cp, 'editor_opening' if pending else 'persisted_script_verified')
            return self.result(cp)
        return self.s.run('geck_compile', {'deadline_seconds': deadline_seconds}, action,
                          request_key=request_key, modifies=True)

    def resume(self, operation_id, extend_seconds=0, reviewed_roundtrip=None, review_note=None):
        def action():
            cp = self.read(operation_id)
            if cp.get('released'):
                return self.result(cp, 'failed', 'Reservation was explicitly released after review. Retained proofs are historical; start a new operation.')
            if cp['phase'] in ('installed', 'reviewed_saved'):
                if (sha(self.p.plugin_path.read_bytes()) != cp['expectedDiskSha256'] or
                        self.auth.compile_context(self.auth.load_spec()) != cp['context']):
                    return self.result(cp, 'blocked', 'Historical compile proof retained; current installed artifact or inputs changed. Start a reviewed new build/compile.')
                return self.result(cp, 'verified', 'Canonical saved artifact retained; spec adoption remains required before rebuilding.' if cp['phase'] == 'reviewed_saved' else 'Complete. Reload GECK before further saves.')
            reservation(self.p.lock_root, self.owner(operation_id))
            if extend_seconds:
                if not 30 <= extend_seconds <= 7200:
                    raise ValueError('extend_seconds must be 30..7200')
                cp['deadlineAt'] = time.time() + extend_seconds
                self.write(cp)
            if time.time() > cp['deadlineAt']:
                return self.result(cp, 'blocked', 'Overall deadline expired; inspect checkpoint and preserve editor work. '
                                   'Resume with extend_seconds after reviewing the current session.')
            spec = self.auth.load_spec()
            if self.auth.compile_context(spec) != cp['context']:
                return self.result(cp, 'blocked', 'Compiler/spec/source/dependencies changed; preserve this checkpoint and reconcile inputs.')
            actual_ids = {key: '%08X' % ((len(spec['masters']) << 24) | value)
                          for key, value in self.auth.formids(spec).assigned.items()}
            if actual_ids != cp['formIds']:
                return self.result(cp, 'blocked', 'FormID map changed; review before continuing.')
            state = self.s.check_session(require_plugin=True, no_dialogs=False)
            disk = self.p.plugin_path.read_bytes()
            disk_hash = sha(disk)
            if state['sessionId'] != cp['sessionId']:
                # UI handles never survive restart. Persisted proofs may survive, after revalidation.
                if self.s.loaded_plugin(state['sessionId']) != cp['expectedDiskSha256'] or disk_hash != cp['expectedDiskSha256']:
                    return self.result(cp, 'blocked', 'Editor restarted. Reload the checkpoint artifact through the bridge after review.')
                if state['unsavedChanges']:
                    return self.result(cp, 'blocked', 'Restarted editor contains unreviewed dirty work.')
                self.verify_completed(cp, spec, disk)
                cp['sessionId'] = state['sessionId']
                cp['loadedSha256'] = disk_hash
                self.write(cp, 'editor_opening' if cp['index'] < len(cp['order']) else 'persisted_script_verified')
            phase = cp['phase']
            if disk_hash != cp['expectedDiskSha256'] and phase != 'plugin_save_requested':
                return self.result(cp, 'blocked', 'Installed artifact changed since checkpoint; stale editor save refused.')
            if cp['index'] < len(cp['order']):
                edid = cp['order'][cp['index']]
                rec = spec['records'][edid]
                text = generic.script_text(self.auth.spec_path.parent, rec, edid, edid)
                expected_source = source_hash(text)
                if phase == 'editor_opening':
                    self.s.call('script.editor.open', session=cp['sessionId'])
                    self.write(cp, 'selecting_script')
                    phase = 'selecting_script'
                if phase == 'selecting_script':
                    self.write(cp, 'selecting_script')
                    observed = self.s.call('script.prepare', edid, session=cp['sessionId'])
                    self.check_source(observed, expected_source)
                    cp['source'] = observed
                    self.write(cp, 'source_verified')
                elif phase == 'source_verified':
                    # After this durable intent, Save is NEVER replayed, even on client cancellation.
                    self.write(cp, 'save_requested')
                    cp['saveDispatch'] = self.s.call('script.save', edid, expected_source, session=cp['sessionId'])
                    self.write(cp, 'busy_dialog_review')
                elif phase in ('save_requested', 'busy_dialog_review'):
                    observed = self.s.call('script.source', edid, session=cp['sessionId'])
                    self.check_source(observed, expected_source)
                    blockers = [w for w in state.get('windows', []) if w['class'] == '#32770' and w.get('visible', True)
                                and not str(w.get('text', '')).startswith('Script Edit')]
                    if blockers:
                        cp['dialogs'] = blockers
                        cp['dialogEvidence'] = self.s.call('script.editor.inspect', session=cp['sessionId'])
                        self.write(cp)
                        if (len(blockers) == 1 and blockers[0].get('text') == 'Save Current Script?'
                                and not cp.get('promptResolutionRequested')):
                            cp['promptResolutionRequested'] = True
                            self.write(cp)  # native helper rechecks owner, EDID, source and Yes button before dispatch
                            cp['promptResolution'] = self.s.call('script.resolveSave', edid, expected_source,
                                                                session=cp['sessionId'])
                            self.write(cp)
                            return self.result(cp, 'pending' if cp['promptResolution'].get('resolved') else 'blocked',
                                               'Owned prompt resolution requires native evidence; inspect retained dialog state.')
                        return self.result(cp, 'blocked', 'Unknown/compile dialog preserved. Inspect controls and resolve it explicitly; no dismissal sent.')
                    # Positive mutation evidence: each script starts at a clean saved boundary.
                    if not state['unsavedChanges'] or not observed.get('editor', {}).get('enabled'):
                        return self.result(cp, 'pending', 'Awaiting plugin mutation and responsive script editor; title asterisk is advisory. Save will not be replayed.')
                    self.write(cp, 'editor_close_requested')
                    cp['saveObservation'] = observed
                    try:
                        closed = self.s.call('script.editor.close', edid, expected_source, session=cp['sessionId'])
                    except BridgeError as error:
                        if error.code != 'MODAL_BLOCKED':
                            raise
                        cp['closeObservation'] = {'code': error.code, 'message': str(error), 'evidence': error.evidence}
                        self.write(cp)
                        return self.result(cp, 'blocked', 'Normal close opened a prompt after Save. Compilation remains unverified; inspect retained closeObservation. No Save or dismissal will be replayed.')
                    if not closed.get('closed'):
                        return self.result(cp, 'blocked', 'Script editor close unverified; plugin save refused.')
                    self.write(cp, 'editor_closed')
                elif phase == 'editor_close_requested':
                    observed = self.s.call('script.editor.inspect', session=cp['sessionId'])
                    if observed.get('editor') is not None and observed['editor'].get('visible', True):
                        return self.result(cp, 'blocked', 'Close did not finish; review the retained editor/dialogs. Plugin save refused.')
                    self.write(cp, 'editor_closed')
                elif phase == 'editor_closed':
                    # Recheck immediately before save under the existing install/editor lock.
                    if sha(self.p.plugin_path.read_bytes()) != cp['expectedDiskSha256']:
                        return self.result(cp, 'blocked', 'Stale installed artifact; plugin save refused.')
                    backup = self.p.state_dir / 'backups' / (self.p.plugin + '.' + disk_hash + '.bak')
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    if not backup.exists():
                        atomic_write(backup, disk)
                    if backup.read_bytes() != disk:
                        raise ValueError('Pre-save backup differs')
                    cp['backup'] = str(backup)
                    self.write(cp, 'plugin_save_requested')
                    cp['pluginSave'] = self.s.call('plugin.save', disk_hash, session=cp['sessionId'])
                    self.write(cp)
                elif phase == 'plugin_save_requested':
                    if state['unsavedChanges'] or disk_hash == cp['expectedDiskSha256']:
                        return self.result(cp, 'pending', 'Awaiting persisted file change and clean editor; plugin Save will not be replayed.')
                    found = generic.extract_compiled(codec.parse(disk))
                    proof = scripts.verify_script(found.get(edid), text, generic.SCRIPT_TYPES[rec.get('script_type', 'object')],
                                                  cp['formIds'][edid])
                    self.verify_references(proof, spec, disk)
                    self.verify_completed(cp, spec, disk)
                    cp['scripts'][edid] = {**proof, 'sourceSha256': expected_source, 'savedSha256': disk_hash,
                                           'sessionId': cp['sessionId'], 'source': cp['source']}
                    cp['expectedDiskSha256'] = cp['loadedSha256'] = disk_hash
                    cp['loadedAt'] = time.time()
                    cp['index'] += 1
                    cp.pop('promptResolutionRequested', None)
                    self.record_saved(cp, disk_hash)
                    self.write(cp, 'editor_opening' if cp['index'] < len(cp['order']) else 'persisted_script_verified')
                else:
                    raise ValueError('Unexpected compile phase ' + phase)
                return self.result(cp)
            if phase == 'persisted_script_verified':
                self.verify_completed(cp, spec, disk)
                # Include verified existing cache hits; they remain bound to this exact context.
                prior = scripts.load_cache(self.p.state_dir, spec['project_id'])
                provenance = {'operationId': operation_id, 'savedSha256': disk_hash, 'context': cp['context'],
                              'scripts': {**{k: v['verification'] for k, v in prior.items()
                                           if v.get('provenance', {}).get('context') == cp['context']}, **cp['scripts']}}
                report = scripts.update_from_plugin(self.p.state_dir, spec, self.auth.spec_path.parent,
                                                    disk, cp['formIds'], provenance)
                if any(not v.startswith('cached (') for v in report.values()):
                    return self.result(cp, 'blocked', 'Saved-script verification failed; last-good cache retained: ' + json.dumps(report))
                cp['cache'] = report
                self.write(cp, 'cached')
            elif phase == 'cached':
                receipt, rebuilt = self.auth.build(write=False)
                if receipt['uncompiledScripts'] or not receipt['validation']['ok']:
                    return self.result(cp, 'blocked', 'Rebuild contains uncompiled scripts or validation failures; install refused.')
                cp['roundtrip'] = roundtrip(disk, rebuilt)
                cp['roundtrip']['assets'] = {'intended': cp.get('intendedAssets'), 'final': receipt.get('assets'),
                                            'matches': cp.get('intendedAssets') == receipt.get('assets')}
                if not cp['roundtrip']['assets']['matches']:
                    return self.result(cp, 'blocked', 'Assets changed since compile start; rebuild/install requires review.')
                if not cp['roundtrip']['complete']:
                    token = sha(json.dumps(cp['roundtrip'], sort_keys=True).encode())
                    cp['roundtripReviewToken'] = token
                    self.write(cp)
                    if reviewed_roundtrip is None:
                        return self.result(cp, 'blocked', 'Semantic roundtrip differences require review; inspect changedRecords/missingRecordsOrOverrides. No rebuilt artifact installed.')
                    if reviewed_roundtrip != token or not isinstance(review_note, str) or len(review_note.strip()) < 12:
                        return self.result(cp, 'blocked', 'Review token/note differs from the current exact saved/rebuilt diff.')
                    if cp['roundtrip']['missingRecordsOrOverrides']:
                        return self.result(cp, 'blocked', 'Missing records/overrides require spec support; cannot waive them with normalization review.')
                    # Explicit reconciliation preserves canonical GECK bytes, never installs the losing rebuild.
                    # It does not edit the spec or claim future rebuilds will reproduce these fields.
                    self.verify_completed(cp, spec, disk)
                    from .esp.validate import validate
                    from .esp.assets import AssetIndex
                    validation = validate(disk, self.auth.index(spec['masters']),
                                          AssetIndex(self.p.game_root / 'Data'), spec['masters'])
                    if not validation['ok']:
                        return self.result(cp, 'blocked', 'Saved artifact failed validation; review cannot waive it.')
                    cp['canonicalReview'] = {'token': token, 'note': review_note, 'savedSha256': disk_hash,
                                             'validation': validation, 'specAdopted': False,
                                             'rebuildInstalled': False, 'time': time.time()}
                    self.write(cp, 'reviewed_saved')
                    reservation(self.p.lock_root, self.owner(operation_id), release=True)
                    return self.result(cp, 'verified', 'Reviewed canonical saved artifact retained. No rebuild installed; adopt field intent in the spec before a future rebuild.')
                written, _ = self.auth.build(write=True)
                if written['sha256'] != receipt['sha256']:
                    raise ValueError('Build inputs changed during roundtrip verification')
                cp['builtSha256'] = written['sha256']
                self.write(cp, 'rebuilt')
            elif phase == 'rebuilt':
                if self.auth.receipt()['sha256'] != cp['builtSha256']:
                    return self.result(cp, 'blocked', 'Built artifact changed; install refused.')
                cp['install'] = self.auth.install(state['editorTitle'])
                cp['expectedDiskSha256'] = cp['builtSha256']
                self.write(cp, 'installed')
                reservation(self.p.lock_root, self.owner(operation_id), release=True)
                return self.result(cp, 'verified', 'Complete. Reload GECK before saving the final installed build.')
            return self.result(cp)
        return self.s.run('geck_compile', {}, action, modifies=True, resume_id=operation_id)

    @staticmethod
    def check_source(observed, expected):
        if observed.get('sourceSha256') != expected or not observed.get('sourceVerified'):
            raise BridgeError('SOURCE_MISMATCH', 'Complete source readback differs; Save not authorized', observed)

    def verify_completed(self, cp, spec, disk):
        found = generic.extract_compiled(codec.parse(disk))
        for edid, proof in cp['scripts'].items():
            rec = spec['records'][edid]
            text = generic.script_text(self.auth.spec_path.parent, rec, edid, edid)
            current = scripts.verify_script(found.get(edid), text, generic.SCRIPT_TYPES[rec.get('script_type', 'object')],
                                             cp['formIds'][edid])
            self.verify_references(current, spec, disk)
            if current != {key: proof[key] for key in current}:
                # JSON converts tuples to lists; canonicalize both before comparing.
                if json.dumps(current, sort_keys=True) != json.dumps({key: proof[key] for key in current}, sort_keys=True):
                    raise ValueError('Previously verified bytecode/dependencies/layout changed: ' + edid)

    def verify_references(self, proof, spec, disk):
        own = {rec.form_id for rec, _ in codec.parse(disk).records()}
        index = self.auth.index(spec['masters'])
        indexed = {(index.masters[row[0]], row[2] & 0xFFFFFF)
                   for rows in index.entries.values() for row in rows}
        for tag, value in proof['references']:
            if tag != 'SCRO':
                continue
            prefix = value >> 24
            if prefix == len(spec['masters']) and value in own:
                continue
            # PlayerRef is an engine-provided persistent reference, absent from ESM indexes.
            if value == 0x00000014 and spec['masters'] and spec['masters'][0] == 'FalloutNV.esm':
                continue
            if prefix < len(spec['masters']) and (spec['masters'][prefix], value & 0xFFFFFF) in indexed:
                continue
            raise ValueError('Unverified compiled reference identity: %08X (index required for master references)' % value)

    def record_saved(self, cp, digest):
        path = self.p.state_dir / 'installs' / (self.p.project_id + '.json')
        history = json.loads(path.read_text()) if path.exists() else []
        history.append({'time': time.time(), 'sha256': digest, 'kind': 'verified-compile-checkpoint',
                        'operationId': cp['operationId'], 'specSha256': cp['specSha256']})
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, (json.dumps(history, indent=1) + '\n').encode())


def roundtrip(saved, rebuilt):
    """Account for all saved record identities, including otherwise unsupported master overrides.

    SCPT bytecode is verified separately; non-script payload changes remain explicit.
    A conservative refusal is preferable to silently discarding an unsupported intent.
    """
    from .esp.diff import record_map, subrecord_diff
    left, right = record_map(codec.parse(saved)), record_map(codec.parse(rebuilt))
    missing, changed, representation = [], [], []
    for key, (record, _) in left.items():
        if key not in right:
            missing.append('%s:%08X' % key)
        elif record.type not in ('TES4', 'SCPT'):
            differences = subrecord_diff(record, right[key][0])
            flag_delta = record.flags ^ right[key][0].flags
            if flag_delta & 0x40000:
                representation.append({'record': '%s:%08X' % key, 'compressionFlagChanged': True})
            if differences or flag_delta & ~0x40000:
                changed.append({'record': '%s:%08X' % key, 'differences': differences,
                                'savedFlags': record.flags, 'rebuiltFlags': right[key][0].flags,
                                'semanticFlagDelta': flag_delta & ~0x40000})
    return {'complete': not missing and not changed, 'missingRecordsOrOverrides': missing,
            'changedRecords': changed, 'representationChanges': representation, 'savedSha256': sha(saved), 'rebuiltSha256': sha(rebuilt),
            'assets': 'validated by the final Authoring.build validation receipt'}
