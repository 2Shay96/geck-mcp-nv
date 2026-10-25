"""Synthetic fault injection for durable compile operations; no Bethesda data."""
from contextlib import closing
import copy
import json
from pathlib import Path
import struct
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from bridge_lock import bottle_lock, reservation
from geck_mcp.authoring import Authoring, sha
from geck_mcp.compilation import Compilation, roundtrip, source_hash
from geck_mcp.config import Project
from geck_mcp.esp import codec, generic, scripts
from geck_mcp.service import Service
from geck_mcp.transport import BridgeError
from tests.test_service import editor_executable, host_launcher


class Editor:
    def __init__(self, project):
        self.p = project
        self.calls = []
        self.session = '123:456'
        self.dirty = False
        self.script = None
        self.script_dirty = False
        self.dialogs = []
        self.delayed = False
        self.close_fails = False
        self.timeout = None
        self.bad_source = False

    def call(self, op, *args, session=None, **kwargs):
        self.calls.append((op, args))
        if session and session != self.session:
            raise BridgeError('STALE_SESSION', 'restart')
        if op == 'status':
            return {'sessionId': self.session, 'executable': editor_executable(self.p),
                    'editorTitle': 'Garden of Eden Creation Kit - [%s]' % self.p.plugin + ('*' if self.dirty else ''),
                    'unsavedChanges': self.dirty, 'windows': self.dialogs}
        if op == 'script.prepare':
            self.script = args[0]
        if op in ('script.prepare', 'script.source'):
            text = generic.script_text(self.p.spec.parent, self.spec['records'][args[0]], args[0], args[0])
            result = {'sourceVerified': True, 'sourceSha256': 'bad' if self.bad_source else source_hash(text),
                      'textLength': len(text), 'dirty': self.script_dirty, 'editor': {'enabled': True}}
        elif op == 'script.save':
            if not self.delayed:
                self.dirty = True
            result = {'compiled': False, 'saveRequested': True}
        elif op == 'script.editor.close':
            result = {'closed': not self.close_fails}
        elif op == 'plugin.save':
            plugin = codec.parse(self.p.plugin_path.read_bytes())
            for rec, _ in plugin.records():
                if rec.type == 'SCPT' and rec.editor_id == self.script:
                    header = bytearray(rec.get('SCHR'))
                    struct.pack_into('<I', header, 8, 4)
                    rec.subrecords = [s for s in rec.subrecords if s.tag not in ('SCHR', 'SCDA')]
                    rec.subrecords += [codec.Subrecord('SCHR', bytes(header)), codec.Subrecord('SCDA', b'code')]
            self.p.plugin_path.write_bytes(codec.write(plugin))
            self.dirty = False
            result = {'fileWriteObserved': True}
        else:
            result = {}
        if op == self.timeout:
            self.timeout = None
            raise BridgeError('OUTCOME_UNKNOWN', 'injected timeout after dispatch', uncertain=True)
        return result


class CompileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.spec = {'schema': 1, 'project_id': 'fixture', 'plugin': 'Fixture.esp', 'masters': ['FalloutNV.esm'],
                     'records': {name: {'type': 'SCPT', 'source': name + '.gek', 'script_type': 'quest'}
                                 for name in ('First', 'Second')}}
        self.specpath = root / 'fixture.json'
        self.specpath.write_text(json.dumps(self.spec))
        for name in self.spec['records']:
            (root / (name + '.gek')).write_text('scn ' + name + '\nbegin GameMode\nend\n')
        self.p = Project(project_id='fixture', **host_launcher(root), game_root=root / 'game',
                         plugin='Fixture.esp', spec=self.specpath, helper=root / 'helper', state_dir=root / 'state')
        self.p.plugin_path.parent.mkdir(parents=True)
        self.auth = Authoring(self.p)
        self.receipt, data = self.auth.build(write=True)
        self.p.plugin_path.write_bytes(data)
        self.editor = Editor(self.p)
        self.editor.spec = self.spec
        self.service = Service(self.p, self.editor)
        self.bind_load()

    def bind_load(self):
        with closing(self.service.db()) as db, db:
            result = {'data': {'sessionId': self.editor.session, 'file': {'sha256': sha(self.p.plugin_path.read_bytes())}}}
            db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?)',
                       ('load-' + self.editor.session, self.p.project_id, str(self.p.lock_root), 'geck_plugin_load',
                        None, '', 'loaded_unverified', json.dumps(result), 1, None))

    def start(self):
        result = self.service.compile_start('fixture-start')
        self.assertTrue(result['ok'], result)
        self.op = result['operationId']
        return result

    def step(self):
        return self.service.compile_resume(self.op)

    def phase(self):
        return Compilation(self.service).read(self.op)['phase']

    def to_saved(self):
        self.start()
        for _ in range(5):
            result = self.step()
            self.assertTrue(result['ok'], result)
        self.assertEqual(self.phase(), 'editor_opening')

    def test_reviewed_canonical_diff_retains_saved_bytes_without_install(self):
        self.start()
        for _ in range(40):
            if self.phase() == 'cached': break
            self.assertTrue(self.step()['ok'])
        self.assertEqual(self.phase(), 'cached')
        before = self.p.plugin_path.read_bytes()
        diff = {'complete':False, 'changedRecords':[{'record':'QUST:01000810', 'differences':[
            {'subrecord':'DATA','change':'changed','a':'10','b':'00'}]}],
            'missingRecordsOrOverrides':[], 'savedSha256':sha(before), 'rebuiltSha256':'b'*64}
        with patch('geck_mcp.compilation.roundtrip', return_value=diff):
            blocked = self.step()
            self.assertEqual(blocked['outcome'], 'blocked')
            token = blocked['data']['roundtripReviewToken']
            wrong = self.service.compile_resume(self.op, reviewed_roundtrip='0'*64, review_note='Reviewed canonical fields')
            self.assertEqual(wrong['outcome'], 'blocked')
            accepted = self.service.compile_resume(self.op, reviewed_roundtrip=token, review_note='Reviewed exact QUST DATA normalization; retain canonical saved bytes')
        self.assertEqual(accepted['outcome'], 'verified', accepted)
        self.assertEqual(self.phase(), 'reviewed_saved')
        self.assertEqual(self.p.plugin_path.read_bytes(), before)
        self.assertFalse(accepted['data']['canonicalReview']['rebuildInstalled'])
        self.assertFalse(accepted['data']['canonicalReview']['specAdopted'])

    def test_interrupted_acknowledgment_finishes_reservation_release(self):
        self.start()
        with closing(self.service.db()) as db, db:
            db.execute('UPDATE operations SET recovery_ack=? WHERE id=?', ('{"reviewed":true}', self.op))
        result = self.service.acknowledge(self.op, self.editor.session, sha(self.p.plugin_path.read_bytes()),
                                           'Finish interrupted reviewed release; preserve source and proof')
        self.assertTrue(result['ok'], result)
        with bottle_lock(self.p.lock_root): self.assertIsNone(reservation(self.p.lock_root))
        self.assertTrue(Compilation(self.service).read(self.op)['released'])

    def test_close_prompt_is_blocked_with_evidence_without_save_replay(self):
        self.start()
        for _ in range(2): self.step()
        original = self.editor.call
        def prompt(op, *args, **kw):
            if op == 'script.editor.close':
                raise BridgeError('MODAL_BLOCKED', 'Save Current Script? Current = First', {'owner':'expected editor'})
            return original(op, *args, **kw)
        self.editor.call = prompt
        result = self.step()
        self.assertEqual(result['outcome'], 'blocked', result)
        self.assertIn('Save Current Script?', result['data']['closeObservation']['message'])
        self.assertFalse(any(op == 'plugin.save' for op, _ in self.editor.calls))
        self.assertEqual(sum(op == 'script.save' for op, _ in self.editor.calls), 1)

    def test_engine_player_reference_is_explicit_and_narrow(self):
        flow = Compilation(self.service)
        flow.verify_references({'references': [('SCRO', 0x14)]}, self.spec, self.p.plugin_path.read_bytes())
        for wrong in (0x00FFFFFE, 0x01000014, 0x02000014):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                flow.verify_references({'references': [('SCRO', wrong)]}, self.spec, self.p.plugin_path.read_bytes())

    def test_full_pipeline_and_restart_reuses_persisted_script(self):
        self.to_saved()
        self.service = Service(self.p, self.editor)  # requesting client restarted
        for _ in range(20):
            result = self.step()
            self.assertTrue(result['ok'], result)
            if result['outcome'] == 'verified':
                break
        self.assertEqual(result['outcome'], 'verified', result)
        self.assertEqual([a[0] for op, a in self.editor.calls if op == 'script.save'], ['First', 'Second'])
        self.assertEqual(set(result['data']['scripts']), {'First', 'Second'})
        self.assertTrue(result['data']['roundtrip']['complete'])
        self.assertEqual(self.service.loaded_plugin(self.editor.session), result['data']['loadedSha256'])
        with bottle_lock(self.p.lock_root):
            self.assertIsNone(reservation(self.p.lock_root))

    def test_lingering_title_asterisk_does_not_prevent_persisted_proof(self):
        self.editor.script_dirty = True
        result = self.start()
        for _ in range(40):
            result = self.step()
            if result['outcome'] != 'pending': break
        self.assertEqual(result['outcome'], 'verified', result)
        close = next(args for op, args in self.editor.calls if op == 'script.editor.close')
        self.assertEqual(close[0], 'First')
        self.assertEqual(len(close[1]), 64)
        self.assertTrue(Compilation(self.service).read(self.op)['scripts']['First'])

    def test_visible_retained_editor_still_blocks_plugin_save(self):
        self.start()
        for _ in range(2): self.step()
        cp = Compilation(self.service).read(self.op)
        cp['phase'] = 'editor_close_requested'
        Compilation(self.service).write(cp)
        original = self.editor.call
        def visible(op, *args, **kw):
            if op == 'script.editor.inspect': return {'editor': {'visible': True}}
            return original(op, *args, **kw)
        self.editor.call = visible
        result = self.step()
        self.assertEqual(result['outcome'], 'blocked', result)
        self.assertFalse(any(op == 'plugin.save' for op, _ in self.editor.calls))

    def test_hidden_retained_editor_is_closed_after_interrupted_close(self):
        self.start()
        for _ in range(2): self.step()
        cp = Compilation(self.service).read(self.op)
        cp['phase'] = 'editor_close_requested'
        Compilation(self.service).write(cp)
        original = self.editor.call
        def hidden(op, *args, **kw):
            if op == 'script.editor.inspect': return {'editor': {'visible': False}}
            return original(op, *args, **kw)
        self.editor.call = hidden
        result = self.step()
        self.assertEqual(result['outcome'], 'pending', result)
        self.assertEqual(self.phase(), 'editor_closed')
        self.assertFalse(any(op == 'plugin.save' for op, _ in self.editor.calls))

    def test_delayed_save_cannot_return_compiled(self):
        self.editor.delayed = True
        self.start()
        self.step()
        self.step()
        for _ in range(12):
            result = self.step()
            self.assertEqual(result['outcome'], 'pending', result)
            self.assertFalse(result['data']['compiled'])
        self.assertEqual(sum(op == 'script.save' for op, _ in self.editor.calls), 1)
        self.assertFalse(any(op == 'plugin.save' for op, _ in self.editor.calls))
        self.editor.dirty = True
        self.assertEqual(self.step()['data']['phase'], 'editor_closed')

    def test_timeout_after_save_resumes_without_replay(self):
        self.start()
        self.step()
        self.editor.timeout = 'script.save'
        result = self.step()
        self.assertEqual(result['outcome'], 'outcome_unknown')
        self.assertEqual(self.phase(), 'save_requested')
        self.service = Service(self.p, self.editor)
        self.assertEqual(self.step()['data']['phase'], 'editor_closed')
        self.assertEqual(sum(op == 'script.save' for op, _ in self.editor.calls), 1)

    def test_selection_timeout_reconciles_existing_editor(self):
        self.start()
        self.editor.timeout = 'script.prepare'
        self.assertFalse(self.step()['ok'])
        self.assertEqual(self.editor.script, 'First')
        self.assertEqual(self.step()['data']['phase'], 'source_verified')

    def test_unknown_wrong_unreadable_dialogs_preserve_work(self):
        for title in ('Select Form', 'Save Current Script?', '<unavailable>', 'Unexpected'):
            with self.subTest(title=title):
                if not hasattr(self, 'op'):
                    self.start(); self.step(); self.step()
                self.editor.dialogs = [{'class': '#32770', 'text': title}]
                result = self.step()
                self.assertEqual(result['outcome'], 'blocked', result)
                self.assertFalse(any(op == 'plugin.save' for op, _ in self.editor.calls))

    def test_failed_close_never_saves_plugin(self):
        self.editor.close_fails = True
        self.start(); self.step(); self.step()
        self.assertEqual(self.step()['outcome'], 'blocked')
        self.assertFalse(any(op == 'plugin.save' for op, _ in self.editor.calls))

    def test_wrong_full_source_never_sends_save(self):
        self.editor.bad_source = True
        self.start()
        self.assertFalse(self.step()['ok'])
        self.assertFalse(any(op == 'script.save' for op, _ in self.editor.calls))

    def test_other_profile_and_cli_cannot_take_reserved_editor(self):
        self.start()
        other = self.p.model_copy(update={'project_id': 'other', 'state_dir': self.p.state_dir.parent / 'other'})
        service = Service(other, self.editor)
        result = service.run('cli-mutation', {}, lambda: {'unexpected': True}, modifies=True)
        self.assertEqual(result['error']['code'], 'EDITOR_RESERVED', result)

    def test_source_and_formid_changes_invalidate_checkpoint(self):
        self.start()
        (self.specpath.parent / 'First.gek').write_text('scn First\n; modified\n')
        result = self.step()
        self.assertEqual(result['outcome'], 'blocked', result)
        self.assertEqual(self.editor.calls[-1][0], 'status')  # only start inspected editor

    def test_stale_installed_artifact_blocks_save(self):
        self.start(); self.step(); self.step(); self.step()
        self.p.plugin_path.write_bytes(self.p.plugin_path.read_bytes() + b'newer')
        result = self.step()
        self.assertEqual(result['outcome'], 'blocked', result)
        self.assertFalse(any(op == 'plugin.save' for op, _ in self.editor.calls))

    def test_plugin_save_timeout_reconciles_saved_artifact(self):
        self.start(); self.step(); self.step(); self.step()
        self.editor.timeout = 'plugin.save'
        self.assertFalse(self.step()['ok'])
        self.assertEqual(self.step()['data']['index'], 1)
        self.assertEqual(sum(op == 'plugin.save' for op, _ in self.editor.calls), 1)

    def test_deadline_never_dispatches_more_ui(self):
        self.start()
        cp = Compilation(self.service).read(self.op)
        cp['deadlineAt'] = 1
        Compilation(self.service).write(cp)
        count = len(self.editor.calls)
        self.assertEqual(self.step()['outcome'], 'blocked')
        self.assertEqual(count, len(self.editor.calls))

    def test_idempotent_start_replays_before_reservation_check(self):
        result = self.start()
        again = self.service.compile_start('fixture-start')
        self.assertTrue(again['replayed'], again)
        self.assertEqual(again['operationId'], result['operationId'])

    def test_editor_restart_revalidates_persisted_work_and_invalidates_ui(self):
        self.to_saved()
        self.editor.session = '124:789'
        self.bind_load()
        result = self.step()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['data']['sessionId'], '124:789')
        self.assertEqual(result['data']['index'], 1)
        self.assertEqual([a[0] for op, a in self.editor.calls if op == 'script.save'], ['First'])

    def test_reviewed_release_retains_proof_but_cannot_resume(self):
        self.start()
        result = self.service.acknowledge(self.op, self.editor.session, sha(self.p.plugin_path.read_bytes()), 'Reviewed clean abandoned operation')
        self.assertTrue(result['ok'], result)
        result = self.step()
        self.assertEqual(result['outcome'], 'failed', result)
        with bottle_lock(self.p.lock_root):
            self.assertIsNone(reservation(self.p.lock_root))

    def test_late_failure_preserves_last_good_cache(self):
        self.to_saved()
        cp = Compilation(self.service).read(self.op)
        path = scripts.cache_path(self.p.state_dir, self.p.project_id)
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"last-good":{"synthetic":true}}\n')
        original = path.read_bytes()
        found = generic.extract_compiled(codec.parse(self.p.plugin_path.read_bytes()))
        provenance = {'scripts': cp['scripts'], 'savedSha256': cp['expectedDiskSha256']}
        report = scripts.update_from_plugin(self.p.state_dir, self.spec, self.specpath.parent,
                    self.p.plugin_path.read_bytes(), cp['formIds'], provenance)
        self.assertFalse(report['Second'].startswith('cached ('))
        self.assertEqual(path.read_bytes(), original)

    def test_corrupt_cached_bytecode_cannot_be_reused(self):
        self.start()
        for _ in range(20):
            result = self.step()
            if result['outcome'] == 'verified':
                break
        self.assertEqual(result['outcome'], 'verified', result)
        path = scripts.cache_path(self.p.state_dir, self.p.project_id)
        cache = json.loads(path.read_text())
        cache['First']['compiled'] = [(tag, b'evil'.hex() if tag == 'SCDA' else raw)
                                      for tag, raw in cache['First']['compiled']]
        path.write_text(json.dumps(cache))
        receipt, _ = self.auth.build()
        self.assertIn('First', receipt['uncompiledScripts'])

    def test_completed_resume_revalidates_current_artifact(self):
        self.start()
        for _ in range(20):
            result = self.step()
            if result['outcome'] == 'verified':
                break
        self.assertEqual(result['outcome'], 'verified', result)
        self.p.plugin_path.write_bytes(b'new installed artifact')
        result = self.step()
        self.assertEqual(result['outcome'], 'blocked', result)
        self.assertFalse(result['data']['compiled'])


class CompileProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_stdio_and_cli_read_the_same_durable_checkpoint(self):
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters
        fixture = CompileTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.start()
        root = Path(__file__).resolve().parents[1]
        project = Path(fixture.tmp.name) / 'project.json'
        project.write_text(fixture.p.model_dump_json())
        parameters = StdioServerParameters(command=sys.executable,
            args=[str(root / 'run_mcp.py'), '--project', str(project)], cwd=str(root))
        async with Client(parameters) as client:
            response = await client.call_tool('geck_compile_status', {'operation_id': fixture.op})
            self.assertFalse(response.is_error, response)
            cli = subprocess.run([sys.executable, str(root / 'compile_scripts.py'), '--project', str(project),
                                  '--operation-id', fixture.op, '--status'], capture_output=True, text=True, timeout=20)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual(json.loads(cli.stdout)['data'], response.structured_content['data'])


class PersistenceTests(unittest.TestCase):
    def script(self, padding=0):
        local = bytearray([padding] * 24)
        struct.pack_into('<I', local, 0, 1)
        local[16] = 1
        fields = [('SCHR', struct.pack('<4sIIIHH', bytes(4), 0, 4, 1, 1, 1).hex()),
                  ('SCDA', b'code'.hex()), ('SCTX', b'scn First\r\nshort Count\r\n'.hex()),
                  ('SLSD', local.hex()), ('SCVR', b'Count\0'.hex())]
        return {'formId': '01000800', 'type': 1, 'text': b'scn First\r\nshort Count\r\n',
                'compiledSize': 4, 'compiled': fields}

    def test_padding_ignored_semantic_indices_preserved(self):
        a, b = self.script(), self.script(255)
        self.assertEqual(scripts.semantic_layout(a['compiled']), scripts.semantic_layout(b['compiled']))
        scripts.verify_script(b, a['text'], 1, '01000800', prior=a)
        b['compiled'][-1] = ('SCVR', b'Wrong\0'.hex())
        with self.assertRaises(ValueError):
            scripts.verify_script(b, a['text'], 1, '01000800', prior=a)

    def test_wrong_source_type_bytecode_header_rejected(self):
        for field, value in [('text', b'scn Other'), ('type', 0), ('compiledSize', 9), ('formId', '01000801')]:
            got = self.script(); got[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                scripts.verify_script(got, self.script()['text'], 1, '01000800')

    def test_only_newline_normalization_is_permitted(self):
        self.assertNotEqual(scripts.normalized(b'abc \r\n'), scripts.normalized(b'abc\n'))

    def test_compression_only_is_representation_semantic_flags_still_block(self):
        from tests.test_service import plugin
        saved, rebuilt = codec.parse(plugin()), codec.parse(plugin())
        saved.groups[0].children[0].flags |= 0x40000
        result = roundtrip(codec.write(saved), codec.write(rebuilt))
        self.assertTrue(result['complete'], result)
        self.assertTrue(result['representationChanges'])
        saved.groups[0].children[0].flags |= 0x400
        result = roundtrip(codec.write(saved), codec.write(rebuilt))
        self.assertFalse(result['complete'])
        self.assertEqual(result['changedRecords'][0]['semanticFlagDelta'], 0x400)

    def test_unrepresented_master_override_is_incomplete(self):
        from tests.test_service import plugin
        original = codec.parse(plugin())
        changed = codec.parse(plugin())
        changed.groups.append(codec.Record('CREA', 0x00001234, _subrecords=[codec.Subrecord('EDID', b'MasterOverride\0')]))
        result = roundtrip(codec.write(changed), codec.write(original))
        self.assertFalse(result['complete'])
        self.assertEqual(result['missingRecordsOrOverrides'], ['CREA:00001234'])
