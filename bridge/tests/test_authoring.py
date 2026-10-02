"""Authoring service (Milestone 2 MCP layer): validate, build, install guards, inspect, lookup."""
import copy
import gzip
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from geck_mcp.config import Project
from geck_mcp.esp import build as builder, codec
from geck_mcp.service import Service
from tests.test_service import FakeTransport

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / 'fixtures'
# Frozen copy of the original 13-reference CoolWorld spec; the live project spec keeps evolving.
SPEC = json.loads((Path(__file__).parent / 'fixtures' / 'coolworld.spec.json').read_text())


class AuthoringServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        data = root / 'game' / 'Data'
        (data / 'meshes' / 'salvatore').mkdir(parents=True)
        shutil.copy(FIXTURES / 'meshes' / 'salvatore_animated_m5_upright.nif',
                    data / 'meshes' / 'salvatore' / 'salvatore_animated_m5_upright.nif')
        (data / 'textures' / 'salvatore').mkdir(parents=True)
        (data / 'textures' / 'salvatore' / 'front_atlas_m5.dds').write_bytes(b'DDS ')
        (root / 'state' / 'index').mkdir(parents=True)
        with gzip.open(root / 'state' / 'index' / 'FalloutNV.esm.json.gz', 'wt') as s:
            json.dump({'master': 'FalloutNV.esm', 'entries': {
                'FacRmFloor01': ['STAT', '00018EE1', None, 'Dungeons\\Facility\\Room\\FacRmFloor01.nif'],
                'FacRmFloor02': ['STAT', '00018EE2', None, 'Dungeons\\Facility\\Room\\FacRmFloor02.nif']}}, s)
        self.spec_path = root / 'coolworld.spec.json'
        self.spec_path.write_text(json.dumps(SPEC))
        self.p = Project(project_id='coolworld', wine=root / 'wine', bottle=root / 'bottle',
                         game_root=root / 'game', plugin='CoolWorld.esp', state_dir=root / 'state',
                         helper=root / 'helper', spec=self.spec_path,
                         records=[dict(editor_id='CoolWorldSalvatore', form_id='01000800')])
        self.transport = FakeTransport(self.p)
        self.service = Service(self.p, self.transport)
        self.data = data

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_is_a_dry_run(self):
        result = self.service.spec_validate()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['data']['validation']['checked']['textures'], 1)
        self.assertFalse((self.p.state_dir / 'formids' / 'coolworld.json').exists())
        self.assertFalse((self.p.state_dir.parent / 'build').exists())
        self.assertEqual(self.transport.calls, [])          # never touched the editor

    def test_inline_spec_errors_are_reported(self):
        spec = copy.deepcopy(SPEC)
        spec['cells']['CoolWorld']['objects'][0]['base'] = '@Nowhere'
        result = self.service.spec_validate(spec)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'SPEC_INVALID')
        self.assertIn('objects[0].base', result['error']['message'])
        self.assertEqual(result['outcome'], 'failed_before_change')

    def test_missing_asset_fails_validation(self):
        (self.data / 'textures' / 'salvatore' / 'front_atlas_m5.dds').unlink()
        result = self.service.plugin_build('b1')
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'VALIDATION_FAILED')
        self.assertFalse((self.p.state_dir.parent / 'build' / 'CoolWorld.esp').exists())

    def test_build_install_and_idempotency(self):
        built = self.service.plugin_build('b1')
        self.assertTrue(built['ok'], built)
        self.assertEqual(built['outcome'], 'built')
        self.assertTrue(self.service.plugin_build('b1')['replayed'])
        installed = self.service.plugin_install('100:123', 'i1')
        self.assertTrue(installed['ok'], installed)
        self.assertEqual(installed['outcome'], 'installed')
        target = self.data / 'CoolWorld.esp'
        self.assertTrue(builder.is_generated(target.read_bytes(), 'coolworld'))
        again = self.service.plugin_install('100:123', 'i2')
        self.assertFalse(again['data']['changed'])
        inspect = self.service.plugin_inspect('installed')['data']
        self.assertTrue(inspect['matchesBuild'])
        cells = {c['editorId']: c['references'] for c in inspect['cells'].values()}
        self.assertEqual(cells, {'CoolWorld': 13})

    def test_install_refuses_foreign_file_without_reason_and_backs_up(self):
        target = self.data / 'CoolWorld.esp'
        original = (FIXTURES / 'plugins' / 'CoolWorld-geck-saved.esp').read_bytes()
        target.write_bytes(original)
        self.service.plugin_build('b1')
        refused = self.service.plugin_install('100:123', 'i1')
        self.assertEqual(refused['error']['code'], 'FOREIGN_PLUGIN')
        self.assertEqual(target.read_bytes(), original)
        ok = self.service.plugin_install('100:123', 'i2', 'Jimbo approved replacing the GECK copy')
        self.assertTrue(ok['ok'], ok)
        self.assertEqual(Path(ok['data']['backup']).read_bytes(), original)

    def test_install_refuses_file_edited_since_install(self):
        self.service.plugin_build('b1')
        self.service.plugin_install('100:123', 'i1')
        target = self.data / 'CoolWorld.esp'
        # Simulate a GECK save: still carries our marker, but the bytes changed.
        plugin = codec.parse(target.read_bytes())
        plugin.header.subrecords = [codec.Subrecord('CNAM', b'DEFAULT\0') if s.tag == 'CNAM' else s
                                    for s in plugin.header.subrecords]
        target.write_bytes(codec.write(plugin))
        spec_file = json.loads(self.spec_path.read_text())
        spec_file['cells']['CoolWorld']['objects'][0]['scale'] = 3.0
        self.spec_path.write_text(json.dumps(spec_file))
        self.service.plugin_build('b2')
        refused = self.service.plugin_install('100:123', 'i2')
        self.assertEqual(refused['error']['code'], 'EDITED_SINCE_INSTALL')

    def test_install_refuses_dirty_editor(self):
        self.service.plugin_build('b1')
        self.transport.dirty = True     # FakeTransport title for Fixture? use CoolWorld title below
        self.transport.project = self.p
        result = self.service.plugin_install('100:123', 'i1')
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'UNSAVED_CHANGES')

    def test_lookup_finds_project_and_master_records(self):
        result = self.service.master_lookup('Floor', 'STAT')['data']
        self.assertEqual([r['editorId'] for r in result['masters']], ['FacRmFloor01', 'FacRmFloor02'])
        self.assertEqual(result['masters'][0]['reference'], '@FacRmFloor01')
        own = self.service.master_lookup('salvatore')['data']['project']
        self.assertEqual(own[0]['reference'], '@CoolWorldSalvatore')

    def test_project_without_spec(self):
        p = self.p.model_copy(update={'spec': None})
        result = Service(p, FakeTransport(p)).spec_validate()
        self.assertEqual(result['error']['code'], 'NO_SPEC')


if __name__ == '__main__':
    unittest.main()
