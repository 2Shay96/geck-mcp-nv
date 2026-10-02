import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from bridge_lock import bottle_lock
from geck_mcp.config import Project, model_asset
from geck_mcp.service import Service
from geck_mcp.transport import BridgeError
from esp_check import file_snapshot


def plugin(model='fixture\\old.nif'):
    def field(tag, value):
        return tag + struct.pack('<H', len(value)) + value
    def record(tag, body, identity=0):
        return struct.pack('<4sIIIIHH', tag, len(body), 0, identity, 0, 15, 0) + body
    body = field(b'EDID', b'FixtureStatic\0') + field(b'MODL', model.encode() + b'\0')
    stat = record(b'STAT', body, 0x01000ADD)
    return record(b'TES4', field(b'MAST', b'FalloutNV.esm\0') + field(b'DATA', b'\0'*8)) + struct.pack('<4sI4sI8s', b'GRUP', 24 + len(stat), b'STAT', 0, b'\0'*8) + stat


class FakeTransport:
    def __init__(self, project):
        self.project, self.calls = project, []
        self.model, self.dirty, self.dialog = 'fixture\\old.nif', False, False
        self.fail_set = False
        self.session = '100:123'

    def call(self, operation, *args, session=None, expected_model=None):
        self.calls.append(operation)
        if session and session != self.session:
            raise BridgeError('STALE_SESSION', 'Editor restarted')
        if operation == 'status':
            return dict(sessionId=self.session,
                        executable='Z:' + str(self.project.game_root / 'GECK.exe').replace('/', '\\'),
                        editorTitle=f'Garden of Eden Creation Kit - [{self.project.plugin}]' + ('*' if self.dirty else ''),
                        unsavedChanges=self.dirty,
                        windows=[{'class': '#32770', 'text': 'Static'}] if self.dialog else [])
        if operation == 'objects.find':
            return {'found': True}
        if operation == 'object.read':
            self.dialog = True
            return {'modelPath': self.model}
        if operation == 'object.cancel':
            self.dialog = False
        if operation == 'object.setModel':
            self.model, self.dirty = args[1], True
            if self.fail_set:
                raise BridgeError('EDITOR_UNRESPONSIVE', 'Readback timed out after mutation')
            return {'committed': True, 'reopenedVerified': True}
        if operation == 'plugin.save':
            self.project.plugin_path.write_bytes(plugin(self.model))
            self.dirty = False
            return {'fileWriteObserved': True}
        return {}


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.p = Project(project_id='test', wine=root/'wine', bottle=root/'bottle',
                         game_root=root/'game', plugin='Fixture.esp', state_dir=root/'state',
                         helper=root/'helper', records=[dict(editor_id='FixtureStatic', form_id='01000ADD')])
        mesh = self.p.game_root/'Data/meshes/fixture'
        mesh.mkdir(parents=True)
        (mesh/'new.nif').write_bytes(b'fixture')
        (mesh/'old.nif').write_bytes(b'fixture')
        self.p.plugin_path.write_bytes(plugin())
        self.transport = FakeTransport(self.p)
        self.service = Service(self.p, self.transport)
        self.hash = file_snapshot(self.p.plugin_path)[0]['sha256']

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, key='edit-1', old='fixture\\old.nif', new='fixture\\new.nif', session='100:123'):
        return self.service.set_model('FixtureStatic', new, old, self.hash, session, key)

    def test_set_then_save_and_independent_disk_read(self):
        result = self.edit()
        self.assertEqual(result['outcome'], 'committed_in_editor')
        self.assertEqual(file_snapshot(self.p.plugin_path)[0]['sha256'], self.hash)
        self.assertFalse(self.transport.dialog)
        saved = self.service.save({'FixtureStatic':'fixture\\new.nif'}, self.hash, '100:123', 'save-1')
        self.assertTrue(saved['ok'], saved)
        self.assertEqual(saved['outcome'], 'saved_verified')
        self.assertEqual(Path(saved['data']['backup']).read_bytes(), plugin())
        self.assertTrue(self.service.validate({'FixtureStatic':'fixture\\new.nif'})['ok'])

    def test_idempotency_survives_service_restart(self):
        original = self.edit()
        calls = len(self.transport.calls)
        self.service = Service(self.p, self.transport)
        repeated = self.edit()
        self.assertEqual(len(self.transport.calls), calls)
        self.assertEqual(repeated['operationId'], original['operationId'])
        self.assertTrue(repeated['replayed'])

    def test_conflicting_key_does_not_dispatch(self):
        self.edit()
        calls = len(self.transport.calls)
        result = self.edit(old='different.nif')
        self.assertEqual(result['error']['code'], 'IDEMPOTENCY_CONFLICT')
        self.assertEqual(len(self.transport.calls), calls)

    def test_historical_replay_survives_asset_removal(self):
        first = self.edit()
        (self.p.game_root/'Data/meshes/fixture/new.nif').unlink()
        repeated = self.edit()
        self.assertTrue(repeated['ok'])
        self.assertTrue(repeated['replayed'])
        self.assertEqual(first['operationId'], repeated['operationId'])

    def test_already_correct_is_success_without_mutation(self):
        result = self.edit(new='fixture\\old.nif')
        self.assertTrue(result['ok'])
        self.assertFalse(result['data']['changed'])
        self.assertNotIn('object.setModel', self.transport.calls)

    def test_partial_failure_blocks_following_work(self):
        self.transport.fail_set = True
        failed = self.edit()
        self.assertEqual(failed['outcome'], 'outcome_unknown')
        result = self.service.read('FixtureStatic', 'editor', '100:123')
        self.assertEqual(result['error']['code'], 'RECOVERY_REQUIRED')
        self.assertTrue(self.service.read('FixtureStatic', 'disk')['ok'])
        self.assertTrue(self.service.status()['ok'])

    def test_explicit_recovery_checks_hash_and_dialogs(self):
        self.transport.fail_set = True
        failed = self.edit()
        result = self.service.acknowledge(failed['operationId'], '100:123', self.hash, 'Reviewed edit and disk')
        self.assertFalse(result['ok'])
        self.transport.dialog = False
        result = self.service.acknowledge(failed['operationId'], '100:123', self.hash, 'Reviewed edit and disk')
        self.assertTrue(result['ok'], result)
        self.assertTrue(self.service.read('FixtureStatic', 'editor', '100:123')['ok'])

    def test_restarted_session_never_edits(self):
        result = self.edit(session='99:456')
        self.assertFalse(result['ok'])
        self.assertNotIn('object.setModel', self.transport.calls)

    def test_external_disk_change_never_edits(self):
        self.p.plugin_path.write_bytes(plugin('fixture\\external.nif'))
        result = self.edit()
        self.assertEqual(result['error']['code'], 'STALE_STATE')
        self.assertNotIn('object.setModel', self.transport.calls)

    def test_unrelated_dialog_is_not_closed(self):
        self.transport.dialog = True
        result = self.service.read('FixtureStatic', 'editor', '100:123')
        self.assertEqual(result['error']['code'], 'MODAL_BLOCKED')
        self.assertNotIn('object.cancel', self.transport.calls)

    def test_file_identity_mismatch(self):
        self.p.plugin_path.write_bytes(plugin().replace(b'\xdd\x0a\x00\x01', b'\xee\x0a\x00\x01'))
        result = self.service.read('FixtureStatic', 'disk')
        self.assertEqual(result['error']['code'], 'IDENTITY_MISMATCH')

    def test_path_escape_and_symlink(self):
        for bad in ['..\\escape.nif', 'C:\\escape.nif', '\\escape.nif', 'meshes\\a.nif', 'a/../b.nif']:
            with self.assertRaises(ValueError):
                model_asset(self.p, bad)
        outside = Path(self.tmp.name)/'outside'
        outside.mkdir()
        (self.p.game_root/'Data/meshes/link').symlink_to(outside)
        with self.assertRaises(ValueError):
            model_asset(self.p, 'link\\outside.nif')

    def test_lock_contention_returns_busy(self):
        with bottle_lock(self.p.bottle):
            result = self.service.status()
        self.assertFalse(result['ok'])
        self.assertIn('EDITOR_BUSY', result['error']['message'])
        self.assertEqual(self.transport.calls, [])

    def test_interrupted_journal_survives_restart(self):
        with self.service.db() as db:
            db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?)',
                       ('interrupted','test',str(self.p.bottle),'edit','key','hash','running',None,0,None))
        service = Service(self.p, self.transport)
        self.assertEqual(service.attach('100:123')['error']['code'], 'RECOVERY_REQUIRED')

    def test_interrupted_replay_is_error_with_full_envelope(self):
        import hashlib
        args = {'value': 1}
        fingerprint = hashlib.sha256(json.dumps(['edit', args], sort_keys=True).encode()).hexdigest()
        with self.service.db() as db:
            db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?)',
                       ('interrupted','test',str(self.p.bottle),'edit','key',fingerprint,'running',None,0,None))
        result = self.service.run('edit', args, lambda: self.fail('must not redispatch'), 'key', True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'OUTCOME_UNKNOWN')
        self.assertTrue(result['replayed'])

    def test_step_evidence_survives_partial_mutation(self):
        self.transport.fail_set = True
        result = self.edit()
        evidence = self.service.operation_evidence(result['operationId'])
        self.assertEqual(evidence['steps'][-1]['operation'], 'object.setModel')
        self.assertEqual(evidence['steps'][-1]['state'], 'failed')
        self.assertTrue(any(s['operation'] == 'object.read' and s['state'] == 'verified'
                            for s in evidence['steps']))

    def test_save_uses_latest_dirty_state(self):
        original = self.transport.call
        def call(operation, *args, **kwargs):
            result = original(operation, *args, **kwargs)
            if operation == 'object.cancel':
                self.transport.dirty = True
            return result
        self.transport.call = call
        result = self.service.save({'FixtureStatic': 'fixture\\old.nif'}, self.hash, '100:123', 'save-drift')
        self.assertTrue(result['ok'], result)
        self.assertIn('plugin.save', self.transport.calls)

    def load(self, key='load-test'):
        return self.service.load_plugin('100:123', 'Garden of Eden Creation Kit - [Fixture.esp]',
                                        self.hash, key, reload=True)

    def test_load_dispatch_and_completion_clear_barrier(self):
        result = self.load()
        self.assertEqual(result['outcome'], 'loading', result)
        self.assertEqual(self.service.attach('100:123')['error']['code'], 'RECOVERY_REQUIRED')
        done = self.service.load_status(result['operationId'])
        self.assertTrue(done['ok'], done)
        self.assertFalse(done['data']['loading'])
        self.assertEqual(done['data']['load']['outcome'], 'loaded_verified')
        self.assertTrue(self.service.attach('100:123')['ok'])
        replay = self.load()
        self.assertTrue(replay['replayed'])
        self.assertEqual(self.transport.calls.count('data.load'), 1)

    def test_load_refuses_unsaved_changes(self):
        self.transport.dirty = True
        result = self.service.load_plugin('100:123','Garden of Eden Creation Kit - [Fixture.esp]*',
                                          self.hash, 'load-dirty', True)
        self.assertEqual(result['error']['code'], 'UNSAVED_CHANGES')
        self.assertNotIn('data.open.inspect', self.transport.calls)

    def test_load_rejects_extra_master_before_dialog(self):
        data = plugin().replace(b'FalloutNV.esm', b'OtherName.esm')
        self.p.plugin_path.write_bytes(data)
        self.hash = file_snapshot(self.p.plugin_path)[0]['sha256']
        result = self.load()
        self.assertEqual(result['error']['code'], 'UNSUPPORTED_MASTERS')
        self.assertNotIn('data.open.inspect', self.transport.calls)

    def test_loading_timeout_preserves_pending_operation(self):
        result = self.load()
        original = self.transport.call
        def call(operation, *args, **kwargs):
            if operation == 'status':
                raise BridgeError('EDITOR_UNRESPONSIVE', 'still loading')
            return original(operation, *args, **kwargs)
        self.transport.call = call
        pending = self.service.load_status(result['operationId'])
        self.assertTrue(pending['ok'])
        self.assertTrue(pending['data']['loading'])
        self.assertEqual(self.service.operation(result['operationId'])['outcome'], 'loading')

    def test_load_status_rejects_restart(self):
        result = self.load()
        self.transport.session = '101:456'
        checked = self.service.load_status(result['operationId'])
        self.assertEqual(checked['error']['code'], 'STALE_SESSION')
        self.assertEqual(self.service.operation(result['operationId'])['outcome'], 'loading')

    def test_reviewed_load_cannot_resume_polling(self):
        result = self.load()
        reviewed = self.service.acknowledge(result['operationId'], '100:123', self.hash, 'Reviewed interrupted load')
        self.assertTrue(reviewed['ok'], reviewed)
        checked = self.service.load_status(result['operationId'])
        self.assertEqual(checked['error']['code'], 'RECOVERY_ACKNOWLEDGED')

    def test_loaded_editor_must_match_disk(self):
        result = self.load()
        self.transport.model = 'fixture\\unexpected.nif'
        checked = self.service.load_status(result['operationId'])
        self.assertEqual(checked['error']['code'], 'STALE_STATE')
        self.assertFalse(self.transport.dialog)
        self.assertEqual(self.service.operation(result['operationId'])['outcome'], 'loading')

    def test_interrupted_load_recovery_allows_empty_editor(self):
        result = self.load()
        original = self.transport.call
        def call(operation, *args, **kwargs):
            value = original(operation, *args, **kwargs)
            if operation == 'status':
                value['editorTitle'] = 'Garden of Eden Creation Kit'
            return value
        self.transport.call = call
        reviewed = self.service.acknowledge(result['operationId'], '100:123', self.hash, 'Reviewed clean empty editor')
        self.assertTrue(reviewed['ok'], reviewed)


if __name__ == '__main__':
    unittest.main()
