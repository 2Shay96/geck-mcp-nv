"""Synchronous GECK workflows. One bottle lock spans every multi-step operation.

Workers finish bounded calls even if the MCP request is cancelled: a dispatched
Windows message cannot be safely undone by killing the waiting client.
"""
from contextlib import closing
import hashlib
import json
import re
import sqlite3
import time
import uuid

from bridge_lock import bottle_lock
from esp_check import file_snapshot, read_model, subrecords, cstring
import struct
from .config import model_asset
from .transport import BridgeError, Transport
from .worker import AutoTransport, PersistentTransport
from .verify import match_cell_references
from .authoring import Authoring, AuthoringError
from .esp.records import SpecError


CAPABILITIES = {
    'version': '0.1.0', 'game': 'Fallout New Vegas', 'recordTypes': ['STAT'],
    'transport': 'stdio', 'editorAdapter': '32-bit Win32 controls under CrossOver',
    'helperTransport': 'persistent worker (Probe.Mcp.exe serve) with automatic one-shot fallback',
    'recordIdentity': 'configured plugin + persisted STAT FormID + exact EditorID',
    'tools': {
        'geck_status': {'effect': 'observe'},
        'geck_inspect_windows': {'effect': 'observe', 'scope': 'bounded GECK control inventory'},
        'geck_project_attach': {'effect': 'observe'},
        'geck_plugin_load': {'effect': 'load configured plugin and FalloutNV.esm; requires clean editor'},
        'geck_plugin_load_status': {'effect': 'observe and reconcile pending load'},
        'geck_records_find': {'effect': 'selection/filter', 'scope': 'configured STAT records'},
        'geck_record_read': {'effect': 'temporary record dialog or disk read'},
        'geck_record_set_model': {'effect': 'editor mutation', 'idempotent': True},
        'geck_preview_open': {'effect': 'preview/selection'},
        'geck_preview_close': {'effect': 'close identified preview'},
        'geck_plugin_validate': {'effect': 'disk read'},
        'geck_plugin_save': {'effect': 'save entire active plugin'},
        'geck_operation_get': {'effect': 'journal read'},
        'geck_recovery_acknowledge': {'effect': 'clear recovery barrier after state review'},
        'geck_spec_validate': {'effect': 'offline build + validation dry run; writes nothing'},
        'geck_plugin_build': {'effect': 'write build/<plugin> and receipt, save FormID map; Data untouched'},
        'geck_plugin_install': {'effect': 'copy build into Data with guards and backup; GECK must reload'},
        'geck_plugin_inspect': {'effect': 'disk read of installed or built plugin'},
        'geck_master_lookup': {'effect': 'search master index and project records'},
        'geck_cell_verify': {'effect': 'compare Cell View with build receipt; optional camera framing'},
        'geck_actor_photo': {'effect': 'build/install/load the throwaway GeckPhotoStudio.esp, frame an NPC_/CREA, '
                             'capture PNG + transparent cut-out; resumable (stage loading -> done)',
                             'never': 'saves or edits the user plugins; discards unsaved edits'},
        'geck_render_capture': {'effect': 'macOS capture of the current Render Window by CGWindowID; no clicks'},
        'geck_image_cutout': {'effect': 'write a transparent PNG of the subject in an existing capture'},
    },
    'authoring': {'recordTypes': ['TES4', 'STAT', 'MSTT', 'LIGH', 'CELL (interior)', 'REFR', 'ACHR', 'ACRE'],
                  'references': '"@EditorID" (project or indexed master) or 8-digit FormID',
                  'formIds': 'stable per project; removed keys retired, never reused'},
    'unsupported': ['editing non-generated plugins through specs', 'multi-master plugin loading',
                    'exterior cells/worldspaces',
                    'automatic rollback', 'animation validation', 'gameplay validation'],
    'verificationLimits': ['32 MiB plugins', 'uncompressed STAT/EDID/MODL only',
                           'no extended XXXX in STAT', 'no visual correctness claim',
                           'active file identified by editor title; master list not verified'],
}


def make_transport(project):
    if project.transport == 'oneshot':
        return Transport(project)
    if project.transport == 'persistent':
        return PersistentTransport(project)
    return AutoTransport(project)


class Service:
    def __init__(self, project, transport=None):
        self.project = project
        self.transport = transport or make_transport(project)
        project.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = project.state_dir / 'operations.sqlite3'
        with closing(self.db()) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY, project TEXT, bottle TEXT, name TEXT,
                request_key TEXT, fingerprint TEXT, state TEXT, result TEXT,
                started REAL, recovery_ack TEXT,
                UNIQUE(project, request_key))''')
            db.execute('''CREATE TABLE IF NOT EXISTS steps (
                operation_id TEXT, sequence INTEGER, operation TEXT, state TEXT,
                evidence TEXT, PRIMARY KEY(operation_id, sequence))''')

    def db(self):
        db = sqlite3.connect(self.db_path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def operation(self, operation_id):
        with closing(self.db()) as db:
            row = db.execute('SELECT * FROM operations WHERE id=? AND project=?',
                             (operation_id, self.project.project_id)).fetchone()
        if row is None:
            raise ValueError('operation not found in this project')
        return json.loads(row['result']) if row['result'] else {
            'ok': False, 'operationId': row['id'], 'operation': row['name'],
            'projectId': row['project'], 'outcome': 'outcome_unknown',
            'data': None, 'elapsedMs': 0,
            'error': {'code': 'OUTCOME_UNKNOWN', 'retrySafe': False,
                      'message': 'Operation is running or interrupted; inspect state before any retry'},
        }

    def operation_evidence(self, operation_id):
        result = self.operation(operation_id)
        with closing(self.db()) as db:
            rows = db.execute('SELECT * FROM steps WHERE operation_id=? ORDER BY sequence',
                              (operation_id,)).fetchall()
        return dict(result, steps=[dict(row, evidence=json.loads(row['evidence'])
                                      if row['evidence'] else None) for row in rows])

    def run(self, name, args, action, request_key=None, modifies=False, editor=True):
        started = time.monotonic()
        operation_id = str(uuid.uuid4())
        fingerprint = hashlib.sha256(json.dumps([name, args], sort_keys=True).encode()).hexdigest()
        began = False
        try:
            if request_key is not None and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', request_key):
                raise ValueError('request_key must be 1..100 simple identifier characters')
            with bottle_lock(self.project.lock_root):
                with closing(self.db()) as db, db:
                    if request_key:
                        row = db.execute('SELECT * FROM operations WHERE project=? AND request_key=?',
                                         (self.project.project_id, request_key)).fetchone()
                        if row:
                            if row['fingerprint'] != fingerprint:
                                raise BridgeError('IDEMPOTENCY_CONFLICT', 'Key already used for different arguments')
                            return dict(self.operation(row['id']), replayed=True)
                    if editor and name not in ('geck_status', 'geck_inspect_windows', 'geck_plugin_load_status', 'geck_recovery_acknowledge'):
                        row = db.execute("SELECT id FROM operations WHERE bottle=? AND state IN ('running','outcome_unknown','loading') AND recovery_ack IS NULL LIMIT 1",
                                         (str(self.project.lock_root),)).fetchone()
                        if row:
                            raise BridgeError('RECOVERY_REQUIRED', 'Uncertain prior operation blocks editor work',
                                              {'operationId': row['id']})
                    db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?)',
                               (operation_id, self.project.project_id, str(self.project.lock_root), name,
                                request_key, fingerprint, 'running', None, time.time(), None))
                began = True
                self._mutation_dispatched = False
                self._active_operation = operation_id
                self._step_sequence = 0
                # Only errors after entering the action may represent partial edits.
                try:
                    data = action()
                    outcome = data.pop('_outcome', 'unchanged')
                    result = {'ok': True, 'operationId': operation_id, 'operation': name,
                              'projectId': self.project.project_id, 'outcome': outcome,
                              'data': data, 'error': None}
                except Exception as e:
                    result = self.failure(e, operation_id, name, modifies and self._mutation_dispatched)
                finally:
                    self._active_operation = None
                result['elapsedMs'] = round((time.monotonic() - started) * 1000)
                with closing(self.db()) as db, db:
                    db.execute('UPDATE operations SET state=?, result=? WHERE id=?',
                               (result['outcome'], json.dumps(result), operation_id))
                return result
        except Exception as e:
            # If journaling failed after dispatch, never describe the call as safe to retry.
            result = self.failure(e, operation_id, name, modifies and began)
            result['elapsedMs'] = round((time.monotonic() - started) * 1000)
            return result

    def failure(self, error, operation_id, name, modifies):
        code = getattr(error, 'code', 'INVALID_ARGUMENT' if isinstance(error, ValueError) else 'BRIDGE_ERROR')
        unknown = modifies or (getattr(error, 'uncertain', False) and name not in
                               ('geck_status', 'geck_inspect_windows', 'geck_plugin_validate', 'geck_project_attach'))
        return {'ok': False, 'operationId': operation_id, 'operation': name,
                'projectId': self.project.project_id,
                'outcome': 'outcome_unknown' if unknown else 'failed_before_change',
                'data': getattr(error, 'evidence', None),
                'error': {'code': code, 'message': str(error),
                          'retrySafe': False,
                          'recovery': 'Read status and operation evidence before retrying.'}}

    def call(self, operation, *args, session=None, expected_model=None):
        operation_id = getattr(self, '_active_operation', None)
        sequence = None
        if operation_id:
            self._step_sequence += 1
            sequence = self._step_sequence
            with closing(self.db()) as db, db:
                db.execute('INSERT INTO steps VALUES (?,?,?,?,?)',
                           (operation_id, sequence, operation, 'dispatching',
                            json.dumps({'arguments': args, 'session': session})))
        if operation in ('object.setModel', 'plugin.save', 'data.load'):
            self._mutation_dispatched = True
        try:
            result = self.transport.call(operation, *args, session=session, expected_model=expected_model)
        except Exception as error:
            if operation_id:
                with closing(self.db()) as db, db:
                    db.execute('UPDATE steps SET state=?, evidence=? WHERE operation_id=? AND sequence=?',
                               ('failed', json.dumps({'error': str(error),
                                 'evidence': getattr(error, 'evidence', None)}), operation_id, sequence))
            raise
        if operation_id:
            with closing(self.db()) as db, db:
                db.execute('UPDATE steps SET state=?, evidence=? WHERE operation_id=? AND sequence=?',
                           ('verified', json.dumps(result), operation_id, sequence))
        return result

    def call_batch(self, steps, session=None):
        """Run read/selection steps in one worker round trip when supported.

        Journaled as one step per helper operation. Never used for mutations.
        """
        if any(op in ('object.setModel', 'plugin.save', 'data.load') for op, *_ in steps):
            raise ValueError('mutating operations are never batched')
        batch = getattr(self.transport, 'batch', None)
        if batch is None:
            return [self.call(op, *args, session=session) for op, *args in steps]
        operation_id = getattr(self, '_active_operation', None)
        label = '+'.join(op for op, *_ in steps)
        sequence = None
        if operation_id:
            self._step_sequence += 1
            sequence = self._step_sequence
            with closing(self.db()) as db, db:
                db.execute('INSERT INTO steps VALUES (?,?,?,?,?)',
                           (operation_id, sequence, 'batch:' + label, 'dispatching',
                            json.dumps({'steps': steps, 'session': session})))
        try:
            results = batch(steps, session=session)
        except Exception as error:
            if operation_id:
                with closing(self.db()) as db, db:
                    db.execute('UPDATE steps SET state=?, evidence=? WHERE operation_id=? AND sequence=?',
                               ('failed', json.dumps({'error': str(error),
                                 'evidence': getattr(error, 'evidence', None)}), operation_id, sequence))
            raise
        if operation_id:
            with closing(self.db()) as db, db:
                db.execute('UPDATE steps SET state=?, evidence=? WHERE operation_id=? AND sequence=?',
                           ('verified', json.dumps(results), operation_id, sequence))
        return results

    def transport_info(self):
        describe = getattr(self.transport, 'describe', None)
        return describe() if describe else {'mode': 'custom'}

    def close(self):
        photo = getattr(self, '_photo', None)
        if photo is not None:
            photo.close()
        close = getattr(self.transport, 'close', None)
        if close:
            close()

    def status(self):
        def action():
            state = self.call('status')
            return dict(state, bridgeTransport=self.transport_info())
        return self.run('geck_status', {}, action)

    def inspect_windows(self, limit):
        return self.run('geck_inspect_windows', {'limit': limit}, lambda: self.call('inspect', limit))

    def check_session(self, session, require_plugin=True, no_dialogs=True):
        state = self.call('status', session=session)
        if state['sessionId'] != session:
            raise BridgeError('STALE_SESSION', 'Editor restarted; attach again')
        # Wine may report C: rather than Z:. Compare through the configured bottle.
        actual = state['executable']
        if self.project.launcher == 'native':
            from pathlib import PureWindowsPath
            same = (PureWindowsPath(actual).as_posix().lower()
                    == PureWindowsPath(self.project.game_root / 'GECK.exe').as_posix().lower())
            if not same:
                raise BridgeError('WRONG_EDITOR', 'Running editor is outside configured game root', state)
            actual_path = None
        elif actual[:3].lower() == 'c:\\':
            actual_path = self.project.bottle / 'drive_c' / actual[3:].replace('\\', '/')
        elif actual[:3].lower() == 'z:\\':
            from pathlib import Path
            actual_path = Path('/' + actual[3:].replace('\\', '/'))
        else:
            raise BridgeError('WRONG_EDITOR', 'Unsupported editor executable path')
        if actual_path is not None and str(actual_path.resolve()).lower() != str((self.project.game_root / 'GECK.exe').resolve()).lower():
            raise BridgeError('WRONG_EDITOR', 'Running editor is outside configured game root', state)
        if require_plugin and state['editorTitle'].rstrip('*') != f'Garden of Eden Creation Kit - [{self.project.plugin}]':
            raise BridgeError('WRONG_PLUGIN', 'Load the configured active plugin before editing', state)
        if no_dialogs:
            blocked = [w for w in state.get('windows', []) if w['class'] == '#32770'
                       and not w['text'].startswith("Preview Object: '")]
            if blocked:
                raise BridgeError('MODAL_BLOCKED', 'Existing dialogs belong to the user or an interrupted operation', blocked)
        return state

    def persisted(self, editor_id):
        configured = self.project.record(editor_id)
        snapshot, data = file_snapshot(self.project.plugin_path)
        record = read_model(data, editor_id)
        if record['formId'].upper() != configured.form_id.upper():
            raise BridgeError('IDENTITY_MISMATCH', 'Persisted FormID differs from configured record', record)
        return snapshot, record

    def attach(self, session):
        def action():
            state = self.check_session(session)
            records = [self.persisted(r.editor_id)[1] for r in self.project.records]
            return {'session': state, 'records': records, 'verificationScope': CAPABILITIES['verificationLimits']}
        return self.run('geck_project_attach', {'session': session}, action)

    def load_plugin(self, session, expected_title, expected_hash, request_key, reload=False):
        def action():
            state = self.check_session(session, require_plugin=False)
            if state['editorTitle'] != expected_title:
                raise BridgeError('STALE_STATE', 'Editor title changed before plugin load', state)
            if state['unsavedChanges']:
                raise BridgeError('UNSAVED_CHANGES', 'Save or resolve existing edits before loading another plugin')
            snapshot, data = file_snapshot(self.project.plugin_path)
            if snapshot['sha256'] != expected_hash:
                raise BridgeError('STALE_STATE', 'Plugin changed before loading', snapshot)
            if data[:4] != b'TES4' or len(data) < 24:
                raise ValueError('Invalid plugin header')
            size = struct.unpack_from('<I', data, 4)[0]
            if size > len(data) - 24:
                raise ValueError('Truncated plugin header')
            masters = [cstring(value) for key, value in subrecords(data[24:24+size]) if key == b'MAST']
            if masters != ['FalloutNV.esm']:
                raise BridgeError('UNSUPPORTED_MASTERS', 'Loader currently supports exactly FalloutNV.esm', {'masters': masters})
            for record in self.project.records:
                self.persisted(record.editor_id)
            if expected_title == f'Garden of Eden Creation Kit - [{self.project.plugin}]' and not reload:
                return {'alreadyLoaded': True, 'sessionId': session, 'file': snapshot}
            self.call('data.open.inspect', session=session)
            selection = self.call('data.load', self.project.plugin, session=session)
            return {'_outcome': 'loading', 'sessionId': session, 'file': snapshot,
                    'dispatch': selection, 'loaded': False,
                    'next': 'Call geck_plugin_load_status with this operationId; do not redispatch.'}
        return self.run('geck_plugin_load', dict(session=session, expected_title=expected_title,
                        expected_hash=expected_hash, reload=reload), action, request_key, modifies=True)

    def load_status(self, operation_id):
        def action():
            previous = self.operation(operation_id)
            with closing(self.db()) as db:
                reviewed = db.execute('SELECT recovery_ack FROM operations WHERE id=?', (operation_id,)).fetchone()
            if reviewed and reviewed['recovery_ack']:
                raise BridgeError('RECOVERY_ACKNOWLEDGED', 'This load was reviewed and released; start a fresh load instead')
            if previous['operation'] != 'geck_plugin_load':
                raise ValueError('Not a plugin-load operation')
            if previous['outcome'] != 'loading':
                return {'load': previous}
            session = previous['data']['sessionId']
            try:
                state = self.check_session(session)
            except BridgeError as error:
                if error.code in ('EDITOR_UNRESPONSIVE', 'WRONG_PLUGIN'):
                    return {'load': previous, 'loading': True, 'lastObservation': str(error)}
                raise
            snapshot, _ = file_snapshot(self.project.plugin_path)
            if snapshot['sha256'] != previous['data']['file']['sha256']:
                raise BridgeError('STALE_STATE', 'Plugin bytes changed during load', snapshot)
            if state['unsavedChanges']:
                raise BridgeError('UNSAVED_CHANGES', 'Editor changed while loading; inspect before proceeding', state)
            # A responsive identified editor and exact configured record readbacks
            # provide stronger completion evidence than the title alone.
            records = []
            for record in self.project.records:
                self.select(record.editor_id, session)
                current = self.call('object.read', record.editor_id, session=session)
                self.call('object.cancel', record.editor_id, session=session)
                persisted = self.persisted(record.editor_id)[1]
                if current['modelPath'] != persisted['modelPath']:
                    raise BridgeError('STALE_STATE', 'Loaded model differs from persisted plugin',
                                      {'editor': current, 'disk': persisted})
                records.append(current)
            cells = self.verify_receipt_cells(session)
            previous['outcome'] = 'loaded_verified'
            previous['data'].update(loaded=True, records=records, cells=cells, session=state)
            with closing(self.db()) as db, db:
                db.execute('UPDATE operations SET state=?, result=? WHERE id=?',
                           ('loaded_verified', json.dumps(previous), operation_id))
            return {'load': previous, 'loading': False}
        return self.run('geck_plugin_load_status', {'operation_id': operation_id}, action)

    def verify_receipt_cells(self, session):
        """For spec projects whose installed plugin is the current build: check every cell's references."""
        spec_path = getattr(self.project, 'spec', None)
        if not spec_path:
            return None
        try:
            receipt = Authoring(self.project).receipt()
        except AuthoringError:
            return None
        snapshot, _ = file_snapshot(self.project.plugin_path)
        if snapshot['sha256'] != receipt['sha256']:
            return {'skipped': 'installed plugin is not the current build'}
        out = {}
        for cell_id in receipt.get('references', {}):
            shown = self.call('cell.refs', cell_id, session=session)
            match = match_cell_references(receipt, cell_id, shown)
            if not match['ok']:
                raise BridgeError('CELL_MISMATCH', 'Loaded cell differs from the build receipt',
                                  {'cell': cell_id, 'match': match})
            out[cell_id] = {k: match[k] for k in ('expected', 'shown', 'matched')}
        return out

    def select(self, editor_id, session):
        self.project.record(editor_id)
        found = self.call_batch([('category.select', 'World Objects/Static'),
                                 ('filter.set', editor_id),
                                 ('objects.find', editor_id)], session=session)[-1]
        if not found['found']:
            raise BridgeError('RECORD_NOT_FOUND', 'Configured record absent from the scoped Object Window', found)

    def find(self, query, offset, limit, session):
        def action():
            self.check_session(session)
            selected = [r for r in self.project.records if query.lower() in r.editor_id.lower()]
            rows = []
            for r in selected[offset:offset + limit]:
                self.persisted(r.editor_id)
                self.select(r.editor_id, session)
                rows.append(r.model_dump())
            return {'scope': 'configured STAT records verified in editor and disk', 'rows': rows,
                    'total': len(selected), 'nextOffset': offset + limit if offset + limit < len(selected) else None,
                    'uiChanged': True}
        return self.run('geck_records_find', dict(query=query, offset=offset, limit=limit, session=session), action)

    def read(self, editor_id, source, session=None):
        def action():
            snapshot, record = self.persisted(editor_id)
            if source == 'disk':
                return {'source': 'disk', 'file': snapshot, 'record': record}
            self.check_session(session)
            self.select(editor_id, session)
            current = self.call('object.read', editor_id, session=session)
            self.call('object.cancel', editor_id, session=session)
            return {'source': 'editor', 'record': dict(record, modelPath=current['modelPath']),
                    'identitySource': 'disk plus exact editor ID in scoped Static dialog', 'dialogClosed': True}
        return self.run('geck_record_read', dict(editor_id=editor_id, source=source, session=session),
                        action, editor=source != 'disk')

    def set_model(self, editor_id, model_path, expected_model, expected_hash, session, request_key):
        def action():
            # Validate after durable replay lookup: a historical receipt remains
            # retrievable even if an asset has since moved or been removed.
            self.project.record(editor_id)
            if not model_asset(self.project, model_path).is_file():
                raise ValueError('model file does not exist under configured meshes root')
            self.check_session(session)
            snapshot, _ = self.persisted(editor_id)
            if snapshot['sha256'] != expected_hash:
                raise BridgeError('STALE_STATE', 'Plugin changed since it was read', snapshot)
            self.select(editor_id, session)
            current = self.call('object.read', editor_id, session=session)
            if current['modelPath'] != expected_model:
                self.call('object.cancel', editor_id, session=session)
                raise BridgeError('STALE_STATE', 'Editor model differs from expected value', current)
            if current['modelPath'] == model_path:
                self.call('object.cancel', editor_id, session=session)
                return {'changed': False, 'modelPath': model_path, 'pluginSaved': False}
            edited = self.call('object.setModel', editor_id, model_path, session=session,
                               expected_model=expected_model)
            self.call('object.cancel', editor_id, session=session)
            return {'_outcome': 'committed_in_editor', 'changed': True, 'edit': edited,
                    'pluginSaved': False, 'dialogClosed': True}
        return self.run('geck_record_set_model', dict(editor_id=editor_id, model_path=model_path,
                        expected_model=expected_model, expected_hash=expected_hash, session=session),
                        action, request_key, modifies=True)

    def preview(self, editor_id, session, opening):
        def action():
            self.check_session(session)
            self.persisted(editor_id)
            if opening:
                self.select(editor_id, session)
            return self.call('preview.open' if opening else 'preview.close', editor_id, session=session)
        name = 'geck_preview_open' if opening else 'geck_preview_close'
        return self.run(name, dict(editor_id=editor_id, session=session), action)

    def validate(self, expected_models):
        def action():
            snapshot, data = file_snapshot(self.project.plugin_path)
            rows = []
            for editor_id, model in expected_models.items():
                configured = self.project.record(editor_id)
                row = read_model(data, editor_id)
                if row['formId'].upper() != configured.form_id.upper() or row['modelPath'] != model:
                    raise BridgeError('PERSISTENCE_MISMATCH', 'Persisted identity or model differs', row)
                rows.append(row)
            return {'file': snapshot, 'records': rows, 'persistenceVerified': True,
                    'verificationScope': CAPABILITIES['verificationLimits']}
        return self.run('geck_plugin_validate', expected_models, action, editor=False)

    def save(self, expected_models, expected_hash, session, request_key):
        def action():
            state = self.check_session(session)
            before, data = file_snapshot(self.project.plugin_path)
            if before['sha256'] != expected_hash:
                raise BridgeError('STALE_STATE', 'Plugin changed before save preflight', before)
            # Every expectation must identify a configured existing record.
            for editor_id, model in expected_models.items():
                model_asset(self.project, model)
                self.persisted(editor_id)
            folder = self.project.state_dir / 'backups'
            folder.mkdir(exist_ok=True)
            backup = folder / (self.project.plugin + '.' + before['sha256'] + '.bak')
            if not backup.exists():
                with backup.open('xb') as stream:
                    stream.write(data)
                    stream.flush()
                    import os
                    os.fsync(stream.fileno())
            if backup.read_bytes() != data:
                raise BridgeError('BACKUP_MISMATCH', 'Recovery copy does not match pre-save bytes')
            # Check the in-editor expectations before dispatch, closing only our dialogs.
            for editor_id, model in expected_models.items():
                self.select(editor_id, session)
                current = self.call('object.read', editor_id, session=session)
                self.call('object.cancel', editor_id, session=session)
                if current['modelPath'] != model:
                    raise BridgeError('STALE_STATE', 'Editor model differs from save expectation', current)
            state = self.check_session(session)
            if state['unsavedChanges']:
                saved = self.call('plugin.save', before['sha256'], session=session)
            else:
                saved = {'changed': False, 'reason': 'editor already clean'}
            after, persisted = file_snapshot(self.project.plugin_path)
            final_state = self.check_session(session)
            if final_state['unsavedChanges']:
                raise BridgeError('SAVE_UNCONFIRMED', 'Editor has pending changes after save verification')
            rows = []
            for editor_id, model in expected_models.items():
                row = read_model(persisted, editor_id)
                if (row['modelPath'] != model or
                        row['formId'].upper() != self.project.record(editor_id).form_id.upper()):
                    raise BridgeError('PERSISTENCE_MISMATCH', 'Saved record differs from expectation', row)
                rows.append(row)
            return {'_outcome': 'saved_verified', 'before': before, 'after': after,
                    'backup': str(backup), 'records': rows, 'save': saved,
                    'persistenceVerified': True, 'saveScope': 'all pending changes in active plugin',
                    'verificationScope': CAPABILITIES['verificationLimits']}
        return self.run('geck_plugin_save', dict(expected_models=expected_models,
                        expected_hash=expected_hash, session=session), action, request_key, modifies=True)

    def cell_verify(self, cell_id, session, receipt, frame_form_id=None):
        """Tier 3: compare Cell View's reference list with a build receipt; optionally frame one reference."""
        def action():
            self.check_session(session)
            if receipt.get('plugin') != self.project.plugin:
                raise ValueError('receipt is for %s, project plugin is %s' % (receipt.get('plugin'), self.project.plugin))
            snapshot, _ = file_snapshot(self.project.plugin_path)
            if snapshot['sha256'] != receipt['sha256']:
                raise BridgeError('STALE_STATE', 'Installed plugin differs from the receipt build', snapshot)
            shown = self.call('cell.refs', cell_id, session=session)
            match = match_cell_references(receipt, cell_id, shown)
            out = {'cell': cell_id, 'match': match, 'columns': shown.get('columns'), 'rows': shown.get('rows')}
            if not match['ok']:
                raise BridgeError('CELL_MISMATCH', 'Cell View does not match the build receipt', out)
            if frame_form_id:
                out['camera'] = self.call('cell.show', cell_id, frame_form_id, session=session)
            return out
        return self.run('geck_cell_verify', dict(cell=cell_id, session=session, sha256=receipt.get('sha256'),
                                                 frame=frame_form_id), action)

    # -- Milestone 2: spec-driven authoring ------------------------------------------------
    def authoring(self):
        return Authoring(self.project)

    def _authoring_call(self, fn):
        try:
            return fn()
        except SpecError as e:
            raise BridgeError('SPEC_INVALID', str(e), {'where': e.where})
        except AuthoringError as e:
            raise BridgeError(e.code, str(e), e.evidence)

    def spec_validate(self, spec=None):
        def action():
            receipt, _ = self._authoring_call(lambda: self.authoring().build(write=False, spec_override=spec))
            out = {k: receipt[k] for k in ('plugin', 'sha256', 'size', 'recordCounts', 'formIds',
                                            'references', 'warnings', 'validation')}
            if not receipt['validation']['ok']:
                raise BridgeError('VALIDATION_FAILED', 'Spec builds but fails validation', out)
            return out
        return self.run('geck_spec_validate', {'inline': spec is not None}, action, editor=False)

    def plugin_build(self, request_key):
        def action():
            receipt, _ = self._authoring_call(lambda: self.authoring().build(write=True))
            if not receipt['validation']['ok']:
                raise BridgeError('VALIDATION_FAILED', 'Build failed validation; nothing written',
                                  receipt['validation'])
            return {'_outcome': 'built', **{k: receipt[k] for k in (
                'plugin', 'sha256', 'size', 'recordCounts', 'references', 'warnings', 'validation', 'written')},
                'next': 'geck_plugin_install, then geck_plugin_load (reload) and geck_cell_verify'}
        spec_path = getattr(self.project, 'spec', None)
        spec_hash = hashlib.sha256(spec_path.read_bytes()).hexdigest() if spec_path and spec_path.exists() else None
        return self.run('geck_plugin_build', {'spec': spec_hash}, action, request_key, editor=False)

    def plugin_install(self, session, request_key, allow_replace_foreign=None):
        def action():
            state = self.check_session(session, require_plugin=False, no_dialogs=False)
            entry = self._authoring_call(lambda: self.authoring().install(state['editorTitle'], allow_replace_foreign))
            if entry.get('changed'):
                entry['_outcome'] = 'installed'
                if entry.get('reloadNeeded'):
                    entry['next'] = 'GECK still shows the old version: geck_plugin_load with reload=true'
            return entry
        return self.run('geck_plugin_install', dict(session=session, foreign=allow_replace_foreign),
                        action, request_key, modifies=True)

    def plugin_inspect(self, which):
        return self.run('geck_plugin_inspect', {'which': which},
                        lambda: self._authoring_call(lambda: self.authoring().inspect(which)), editor=False)

    def master_lookup(self, query, record_type=None, limit=25):
        return self.run('geck_master_lookup', dict(query=query, type=record_type, limit=limit),
                        lambda: self._authoring_call(lambda: self.authoring().lookup(query, record_type, limit)),
                        editor=False)

    def cell_verify_ref(self, cell_id, session, frame_ref_id=None):
        receipt = self._authoring_call(lambda: self.authoring().receipt())
        frame = None
        if frame_ref_id:
            refs = [r for r in receipt['references'].get(cell_id, []) if r['refId'] == frame_ref_id]
            if len(refs) != 1:
                raise ValueError('ref_id %r is not in the build receipt for %s' % (frame_ref_id, cell_id))
            frame = refs[0]['formId']
        return self.cell_verify(cell_id, session, receipt, frame)

    def acknowledge(self, operation_id, session, expected_hash, note):
        def action():
            previous = self.operation(operation_id)
            self.check_session(session, require_plugin=previous['operation'] != 'geck_plugin_load', no_dialogs=True)
            snapshot, _ = file_snapshot(self.project.plugin_path)
            if snapshot['sha256'] != expected_hash:
                raise BridgeError('STALE_STATE', 'Disk changed during recovery review')
            with closing(self.db()) as db, db:
                row = db.execute('SELECT * FROM operations WHERE id=? AND project=?',
                                 (operation_id, self.project.project_id)).fetchone()
                if row is None or row['state'] not in ('running', 'outcome_unknown', 'loading'):
                    raise ValueError('operation is not an unresolved operation in this project')
                db.execute('UPDATE operations SET recovery_ack=? WHERE id=?',
                           (json.dumps(dict(session=session, file=snapshot, note=note, time=time.time())), operation_id))
            return {'acknowledged': operation_id, 'note': note,
                    'warning': 'Barrier cleared; this is not rollback or proof of the prior result'}
        return self.run('geck_recovery_acknowledge', dict(operation_id=operation_id, session=session,
                        expected_hash=expected_hash, note=note), action)

    # -- Photo workflow (geck_mcp/photo.py, geck_mcp/imaging.py) -------------------------------
    def photo_studio(self):
        if getattr(self, '_photo', None) is None:
            from .photo import PhotoStudio
            self._photo = PhotoStudio(self.project, lambda project: Service(project))
        return self._photo

    def _envelope(self, name, started, fn):
        from .imaging import ImagingError
        try:
            data = fn()
            error, ok = None, True
        except (BridgeError, ImagingError, AuthoringError) as e:
            data, ok = getattr(e, 'evidence', None), False
            error = {'code': e.code, 'message': str(e), 'retrySafe': e.code not in ('OUTCOME_UNKNOWN',)}
        except (ValueError, SpecError) as e:
            data, ok = None, False
            error = {'code': 'INVALID_ARGUMENT', 'message': str(e), 'retrySafe': True}
        except RuntimeError as e:
            data, ok = None, False
            error = {'code': 'EDITOR_BUSY' if 'EDITOR_BUSY' in str(e) else 'BRIDGE_ERROR', 'message': str(e),
                     'retrySafe': 'EDITOR_BUSY' in str(e)}
        outcome = 'failed_before_change'
        if ok:
            outcome = {'loading': 'loading', 'done': 'captured'}.get((data or {}).get('stage'), 'captured')
        return {'ok': ok, 'operationId': (data or {}).get('operationId') or str(uuid.uuid4()), 'operation': name,
                'projectId': self.project.project_id, 'outcome': outcome, 'data': data, 'error': error,
                'elapsedMs': round((time.monotonic() - started) * 1000)}

    def actor_photo(self, subject, rotation=180, pitch=None, fill=0.86, lighting='auto', render_size=None):
        from .photo import DEFAULT_PITCH
        started = time.monotonic()
        return self._envelope('geck_actor_photo', started, lambda: self.photo_studio().photo(
            subject, rotation=rotation, pitch=DEFAULT_PITCH if pitch is None else pitch, fill=fill,
            lighting=lighting, render_size=render_size))

    def render_capture(self, cutout=False):
        from . import imaging
        from .photo import MAC_TITLE_BAR_POINTS

        def action():
            window = imaging.render_window()
            folder = self.project.state_dir.parent / 'photos'
            stamp = time.strftime('%Y%m%d-%H%M%S')
            raw = imaging.capture_window(window['id'], folder / ('render-%s-raw.png' % stamp))
            _, Image = imaging._np()
            image = Image.open(raw)
            top = int(round(MAC_TITLE_BAR_POINTS * image.width / float(window['bounds']['Width'])))
            path = folder / ('render-%s.png' % stamp)
            image.crop((0, top, image.width, image.height)).convert('RGB').save(path)
            raw.unlink()
            out = {'photo': str(path), 'size': [image.width, image.height - top], 'window': window['title']}
            if cutout:
                out['cutout'] = imaging.cutout(path, folder / ('render-%s-cutout.png' % stamp))
            return out
        return self._envelope('geck_render_capture', time.monotonic(), action)

    def image_cutout(self, path, tolerance=30, chroma_tolerance=22):
        from . import imaging
        from pathlib import Path

        def action():
            src = Path(path).expanduser().resolve(strict=True)
            if src.suffix.lower() != '.png':
                raise ValueError('path must be a .png file')
            return {'cutout': imaging.cutout(src, src.with_name(src.stem + '-cutout.png'),
                                             tolerance=tolerance, chroma_tolerance=chroma_tolerance)}
        return self._envelope('geck_image_cutout', time.monotonic(), action)
