"""Spec-driven plugin authoring for a configured project (Milestone 2).

Shared by the CLIs (build_plugin.py, install_plugin.py) and the MCP tools. Paths:
  <bridge>/build/<Plugin>.esp and <Plugin>.receipt.json     build outputs
  <state_dir>/formids/<project_id>.json                     stable FormID map
  <state_dir>/index/<master>.json.gz                        master indexes (esm_index.py)
  <state_dir>/installs/<project_id>.json                    install history
  <state_dir>/backups/<Plugin>.<sha256>.bak                 anything an install replaced
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from .esp import build as builder, codec, diff, scripts
from .esp.assets import AssetIndex
from .esp.formids import FormIdMap, MasterIndex
from .esp.records import SpecError
from .esp.validate import validate


def sha(data):
    return hashlib.sha256(data).hexdigest()


class AuthoringError(ValueError):
    def __init__(self, code, message, evidence=None):
        super().__init__(message)
        self.code, self.evidence = code, evidence


class Authoring:
    def __init__(self, project, spec_path=None, build_dir=None):
        self.project = project
        self.spec_path = Path(spec_path) if spec_path else getattr(project, 'spec', None)
        if not self.spec_path:
            raise AuthoringError('NO_SPEC', 'Project %s has no "spec" configured' % project.project_id)
        self.build_dir = Path(build_dir) if build_dir else project.state_dir.parent / 'build'
        self.data_dir = project.game_root / 'Data'

    # -- inputs -----------------------------------------------------------------------
    def load_spec(self, override=None):
        spec = builder.check_spec(override) if override is not None else builder.load_spec(self.spec_path.read_text())
        if spec['plugin'] != self.project.plugin:
            raise SpecError('plugin', 'spec builds %s but the project is configured for %s'
                            % (spec['plugin'], self.project.plugin))
        return spec

    def index(self, masters):
        folder = self.project.state_dir / 'index'
        files = [folder / (m + '.json.gz') for m in masters]
        return MasterIndex([f for f in files if f.exists()])

    def formids(self, spec):
        return FormIdMap(self.project.state_dir / 'formids' / (spec['project_id'] + '.json'), spec['plugin'])

    @property
    def built_path(self):
        return self.build_dir / self.project.plugin

    @property
    def receipt_path(self):
        return self.build_dir / (Path(self.project.plugin).stem + '.receipt.json')

    def receipt(self):
        if not self.receipt_path.exists():
            raise AuthoringError('NOT_BUILT', 'No build receipt yet; build first')
        return json.loads(self.receipt_path.read_text())

    # -- build ---------------------------------------------------------------------------
    def build(self, write=False, spec_override=None, adopt=None, check_assets=True, compare=None):
        """Build (and validate) the plugin. Without write, nothing is saved (a dry run)."""
        spec = self.load_spec(spec_override)
        formids = self.formids(spec)
        if adopt is not None:
            if formids.assigned or formids.retired:
                raise SpecError('adopt', 'FormID map already exists; adoption is only for the first build')
            builder.adopt_existing(formids, spec, Path(adopt).read_bytes())
        index = self.index(spec['masters'])
        data, receipt = builder.build(spec, formids, index, base_dir=self.spec_path.parent,
                                      script_cache=scripts.load_cache(self.project.state_dir, spec['project_id']))
        assets = AssetIndex(self.data_dir) if check_assets and self.data_dir.is_dir() else None
        receipt['validation'] = validate(data, index, assets, spec['masters'])
        missing = [m for m in spec['masters'] if m not in index.masters]
        if missing:
            receipt['validation']['warnings'].append('no index for %s: master references unchecked '
                                                     '(run esm_index.py)' % ', '.join(missing))
        if assets is None:
            receipt['validation']['warnings'].append('asset checks skipped (game Data folder not available)')
        if compare is not None:
            receipt['comparedWith'] = str(compare)
            receipt['differences'] = diff.diff(Path(compare).read_bytes(), data)
        receipt['written'] = False
        if write and receipt['validation']['ok']:
            self.build_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(self.built_path, data)
            receipt['written'] = True
            atomic_write(self.receipt_path, (json.dumps(receipt, indent=1) + '\n').encode())
            formids.save()
        return receipt, data

    # -- install ---------------------------------------------------------------------------
    def install(self, editor_title=None, allow_replace_foreign=None):
        """Copy the current build into Data with guards; returns the install record."""
        receipt = self.receipt()
        built = self.built_path.read_bytes()
        if sha(built) != receipt['sha256']:
            raise AuthoringError('STALE_BUILD', 'build output does not match its receipt; rebuild first')
        spec_id = receipt['projectId']
        if not builder.is_generated(built, spec_id):
            raise AuthoringError('NOT_GENERATED', 'build output lacks the generated marker')
        plugin = self.project.plugin
        title = editor_title or ''
        if title.rstrip('*').endswith('[%s]' % plugin) and title.endswith('*'):
            raise AuthoringError('UNSAVED_CHANGES', 'GECK has %s open with unsaved changes; '
                                 'save or discard them before installing' % plugin)
        history_path = self.project.state_dir / 'installs' / (spec_id + '.json')
        history = json.loads(history_path.read_text()) if history_path.exists() else []
        target = self.data_dir / plugin
        previous = target.read_bytes() if target.exists() else None
        previous_sha = sha(previous) if previous is not None else None
        loaded = title.rstrip('*').endswith('[%s]' % plugin)
        if previous_sha == receipt['sha256']:
            return {'changed': False, 'sha256': previous_sha, 'installed': str(target),
                    'reloadNeeded': False}
        foreign = None
        if previous is not None:
            if not builder.is_generated(previous, spec_id):
                if not allow_replace_foreign:
                    raise AuthoringError('FOREIGN_PLUGIN', '%s in Data was not generated by project %s '
                                         '(sha %s). Pass allow_replace_foreign with a reason to replace it; '
                                         'it will be backed up.' % (plugin, spec_id, previous_sha[:12]),
                                         {'sha256': previous_sha})
                foreign = allow_replace_foreign
            elif history and previous_sha != history[-1]['sha256']:
                raise AuthoringError('EDITED_SINCE_INSTALL', '%s in Data changed since the last install '
                                     '(saved from GECK?). Move those edits into the spec first.' % plugin,
                                     {'sha256': previous_sha, 'lastInstalled': history[-1]['sha256']})
        backup = None
        if previous is not None:
            folder = self.project.state_dir / 'backups'
            folder.mkdir(parents=True, exist_ok=True)
            backup = folder / ('%s.%s.bak' % (plugin, previous_sha))
            if not backup.exists():
                atomic_write(backup, previous)
            if sha(backup.read_bytes()) != previous_sha:
                raise AuthoringError('BACKUP_FAILED', 'backup verification failed; nothing installed')
        atomic_write(target, built)
        if sha(target.read_bytes()) != receipt['sha256']:
            raise AuthoringError('INSTALL_MISMATCH', 'installed bytes differ from the build')
        entry = {'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'plugin': plugin, 'sha256': receipt['sha256'],
                 'previousSha256': previous_sha, 'backup': str(backup) if backup else None,
                 'replacedForeign': foreign, 'editorTitle': title or None, 'specSha256': receipt['specSha256']}
        history.append(entry)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(history_path, (json.dumps(history, indent=1) + '\n').encode())
        return dict(entry, changed=True, installed=str(target), reloadNeeded=loaded)

    # -- read-only helpers -------------------------------------------------------------------
    def inspect(self, which='installed'):
        path = self.data_dir / self.project.plugin if which == 'installed' else self.built_path
        if not path.exists():
            raise AuthoringError('NOT_FOUND', '%s plugin not found: %s' % (which, path))
        data = path.read_bytes()
        plugin = codec.parse(data)
        types, cells = {}, {}
        for rec, groups in plugin.records():
            types[rec.type] = types.get(rec.type, 0) + 1
            if rec.type == 'CELL':
                cells['%08X' % rec.form_id] = {'editorId': rec.editor_id, 'references': 0}
            if rec.type in ('REFR', 'ACHR', 'ACRE'):
                owner = [g for g in groups if g.group_type in (8, 9, 10)]
                if owner:
                    key = '%08X' % int.from_bytes(owner[-1].label, 'little')
                    cells.setdefault(key, {'editorId': None, 'references': 0})['references'] += 1
        header = plugin.header
        return {'which': which, 'path': str(path), 'sha256': sha(data), 'size': len(data),
                'masters': [codec.cstring(s.data) for s in header.subrecords if s.tag == 'MAST'],
                'author': codec.cstring(header.get('CNAM')) if header.get('CNAM') else None,
                'generated': builder.is_generated(data, self.load_spec()['project_id']),
                'recordCounts': types, 'cells': cells,
                'matchesBuild': self.receipt_path.exists() and sha(data) == self.receipt()['sha256']}

    def lookup(self, query, record_type=None, limit=25):
        spec = self.load_spec()
        index = self.index(spec['masters'])
        own = []
        for edid, rec in spec.get('records', {}).items():
            if query.lower() in edid.lower() and (record_type is None or rec['type'] == record_type):
                own.append({'editorId': edid, 'type': rec['type'], 'source': spec['plugin'], 'reference': '@' + edid})
        rows = index.search(query, record_type, limit)
        for row in rows:
            row['reference'] = '@' + row['editorId']
        return {'query': query, 'type': record_type, 'project': own, 'masters': rows,
                'indexedMasters': index.masters}


def atomic_write(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
