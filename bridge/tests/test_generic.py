"""Generic (template-cloned) records: ALCH support and where record templates are looked up (fix 4)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from geck_mcp.authoring import Authoring, index_files
from geck_mcp.config import Project
from geck_mcp.esp import build as builder, codec, generic
from geck_mcp.esp.formids import FormIdMap
from geck_mcp.esp.records import SpecError
from tests.test_service import host_launcher

ROOT = Path(__file__).resolve().parent.parent


def alch_template(name='Remote', value=b'\x05\x00\x00\x00'):
    """A minimal ALCH record dump in the format tools/esm_research.py writes."""
    def sub(tag, data):
        return {'tag': tag, 'size': len(data), 'hex': data.hex()}
    return {'type': 'ALCH', 'formId': '00012345', 'flags': 0, 'subrecords': [
        sub('EDID', b'NVRepairKit\0'), sub('FULL', name.encode() + b'\0'), sub('DATA', value)]}


SPEC = {'schema': 1, 'project_id': 'alchtest', 'plugin': 'AlchTest.esp', 'author': 'tests', 'masters': ['FalloutNV.esm'],
        'records': {'TestRemote': {'type': 'ALCH', 'template': 'TestAidTemplate',
                                   'fields': [{'tag': 'FULL', 'text': 'Test Remote'}]}}}


def write_template(state, name='TestAidTemplate', **kw):
    folder = Path(state) / 'templates' / 'FalloutNV.esm'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (name + '.json')).write_text(json.dumps(alch_template(**kw)))


class GenericTypes(unittest.TestCase):
    def test_alch_is_a_generic_type(self):
        # The Salvatore "Ganacci Remote" aid item is an ALCH cloned from a vanilla template.
        self.assertIn('ALCH', generic.GENERIC_TYPES)
        self.assertEqual(builder.check_spec(json.loads(json.dumps(SPEC)))['records']['TestRemote']['type'], 'ALCH')

    def test_alch_from_explicit_fields_builds(self):
        spec = {'schema': 1, 'project_id': 'alchtest', 'plugin': 'AlchTest.esp', 'masters': ['FalloutNV.esm'],
                'records': {'TestRemote': {'type': 'ALCH', 'fields': [{'tag': 'FULL', 'text': 'Remote'},
                                                                      {'tag': 'DATA', 'float': 1.0}]}}}
        with tempfile.TemporaryDirectory() as tmp:
            data, receipt = builder.build(spec, FormIdMap(Path(tmp) / 'f.json', 'AlchTest.esp'))
        self.assertEqual(receipt['recordCounts'].get('ALCH'), 1)
        rec = [r for r, _ in codec.parse(data).records() if r.type == 'ALCH'][0]
        self.assertEqual(rec.editor_id, 'TestRemote')
        self.assertEqual(rec.get('FULL'), b'Remote\0')


class TemplateLookup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_state_dir_first_then_code_root(self):
        dirs = generic.template_dirs(self.root / 'state')
        self.assertEqual(dirs, [self.root / 'state' / 'templates', generic.TEMPLATE_DIR])
        self.assertEqual(generic.template_dirs(None), [generic.TEMPLATE_DIR])
        self.assertEqual(generic.template_dirs(ROOT / 'state'), [generic.TEMPLATE_DIR])   # no duplicate

    def test_missing_template_names_every_folder_tried(self):
        with self.assertRaises(SpecError) as caught:
            generic.load_template('NoSuchTemplate', dirs=generic.template_dirs(self.root / 'state'))
        self.assertIn(str(self.root / 'state' / 'templates'), str(caught.exception))
        self.assertIn(str(generic.TEMPLATE_DIR), str(caught.exception))

    def test_project_state_templates_win(self):
        write_template(self.root / 'state', name='TestAidTemplate', value=b'\x07\x00\x00\x00')
        master, tpl = generic.load_template('TestAidTemplate', dirs=generic.template_dirs(self.root / 'state'))
        self.assertEqual(master, 'FalloutNV.esm')
        self.assertEqual(tpl['subrecords'][2]['hex'], '07000000')

    def test_authoring_builds_from_profile_state_dir(self):
        # Job 038: the template existed only in the profile's state_dir, and the build looked in the code root.
        state = self.root / 'workshop' / 'state'
        write_template(state)
        spec_path = self.root / 'workshop' / 'alch.spec.json'
        spec_path.write_text(json.dumps(SPEC))
        (self.root / 'game' / 'Data').mkdir(parents=True)
        project = Project(project_id='alchtest', **host_launcher(self.root), game_root=self.root / 'game',
                          plugin='AlchTest.esp', state_dir=state, helper=self.root / 'helper', spec=spec_path)
        auth = Authoring(project)
        receipt, data = auth.build(write=True)
        self.assertTrue(receipt['validation']['ok'], receipt['validation'])
        self.assertEqual(receipt['recordCounts'].get('ALCH'), 1)
        self.assertEqual(auth.build_dir, self.root / 'workshop' / 'build')
        self.assertTrue((self.root / 'workshop' / 'build' / 'AlchTest.esp').exists())
        rec = [r for r, _ in codec.parse(data).records() if r.type == 'ALCH'][0]
        self.assertEqual(rec.get('FULL'), b'Test Remote\0')
        self.assertEqual(rec.get('DATA'), b'\x05\x00\x00\x00')

    def test_index_falls_back_to_code_root(self):
        state = self.root / 'state'
        (state / 'index').mkdir(parents=True)
        own = state / 'index' / 'Own.esm.json.gz'
        own.write_bytes(b'')
        files = index_files(state, ['Own.esm', 'NotIndexedAnywhere.esm'])
        self.assertEqual(files, [own])

    def test_build_plugin_cli_uses_state_for_templates_and_output(self):
        state = self.root / 'mod' / 'state'
        write_template(state)
        spec_path = self.root / 'alch.spec.json'
        spec_path.write_text(json.dumps(SPEC))
        dry = subprocess.run([sys.executable, str(ROOT / 'build_plugin.py'), str(spec_path), '--state', str(state),
                              '--dry-run', '--no-assets'], capture_output=True, text=True, cwd=str(ROOT))
        summary = json.loads(dry.stdout.strip().splitlines()[-1])
        self.assertTrue(summary['ok'], dry.stdout + dry.stderr)
        self.assertFalse((self.root / 'mod' / 'build').exists())
        real = subprocess.run([sys.executable, str(ROOT / 'build_plugin.py'), str(spec_path), '--state', str(state),
                               '--no-assets'], capture_output=True, text=True, cwd=str(ROOT))
        summary2 = json.loads(real.stdout.strip().splitlines()[-1])
        self.assertEqual(summary2['sha256'], summary['sha256'])
        self.assertEqual(Path(summary2['out']), self.root / 'mod' / 'build')
        self.assertTrue((self.root / 'mod' / 'build' / 'AlchTest.esp').exists())
        self.assertTrue((self.root / 'mod' / 'build' / 'AlchTest.receipt.json').exists())


if __name__ == '__main__':
    unittest.main()
