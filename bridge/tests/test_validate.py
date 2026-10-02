"""Offline validation (structure + assets), BSA listing and NIF texture scan."""
import copy
import gzip
import json
from pathlib import Path
import struct
import tempfile
import unittest

from geck_mcp.esp import build, codec
from geck_mcp.esp.assets import AssetError, AssetIndex, bsa_names, nif_textures
from geck_mcp.esp.formids import FormIdMap, MasterIndex
from geck_mcp.esp.validate import validate

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / 'fixtures'
# Frozen copy of the original 13-reference CoolWorld spec; the live project spec keeps evolving.
SPEC = json.loads((Path(__file__).parent / 'fixtures' / 'coolworld.spec.json').read_text())
NIF = (FIXTURES / 'meshes' / 'salvatore_animated_m5_upright.nif').read_bytes()


def make_bsa(path, files):
    """Write a minimal uncompressed FNV BSA (v104) containing {'folder\\name': bytes}."""
    folders = {}
    for rel, data in files.items():
        folder, name = rel.rsplit('\\', 1)
        folders.setdefault(folder, []).append((name, data))
    names = b''.join(n.encode() + b'\0' for f in folders.values() for n, _ in f)
    folder_names = sum(len(f) + 1 for f in folders)
    out = bytearray(struct.pack('<4s8I', b'BSA\0', 104, 36, 3, len(folders), len(files),
                                folder_names, len(names), 0))
    out += b''.join(struct.pack('<QII', 0, len(f), 0) for f in folders.values())
    for folder, entries in folders.items():
        out += bytes([len(folder) + 1]) + folder.encode() + b'\0'
        out += b''.join(struct.pack('<QII', 0, len(d), 0) for _, d in entries)
    out += names
    Path(path).write_bytes(bytes(out))


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        with gzip.open(root / 'FalloutNV.esm.json.gz', 'wt') as s:
            json.dump({'master': 'FalloutNV.esm', 'entries': {
                'FacRmFloor01': ['STAT', '00018EE1', None, 'Dungeons\\Facility\\Room\\FacRmFloor01.nif']}}, s)
        self.index = MasterIndex([root / 'FalloutNV.esm.json.gz'])
        self.data_dir = root / 'Data'
        mesh = self.data_dir / 'meshes' / 'Salvatore'
        mesh.mkdir(parents=True)
        (mesh / 'Salvatore_Animated_M5_Upright.NIF').write_bytes(NIF)   # case differs on purpose
        tex = self.data_dir / 'textures' / 'salvatore'
        tex.mkdir(parents=True)
        (tex / 'front_atlas_m5.dds').write_bytes(b'DDS ')
        make_bsa(self.data_dir / 'Fallout - Meshes.bsa',
                 {'meshes\\dungeons\\facility\\room\\facrmfloor01.nif': b'x'})
        self.formids = root / 'formids.json'

    def tearDown(self):
        self.tmp.cleanup()

    def built(self, spec=SPEC):
        m = FormIdMap(self.formids, 'CoolWorld.esp')
        build.adopt_existing(m, spec, (FIXTURES / 'plugins' / 'CoolWorld.esp').read_bytes())
        return build.build(spec, m, self.index)[0]

    def check(self, data, assets=True):
        return validate(data, self.index, AssetIndex(self.data_dir) if assets else None, ['FalloutNV.esm'])

    def test_coolworld_build_passes_everything(self):
        result = self.check(self.built())
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['checked'], {'records': 18, 'groups': 7, 'references': 13,
                                             'models': 1, 'textures': 1})

    def test_real_geck_saved_plugins_pass_structure(self):
        for name in ('CoolWorld-geck-saved.esp', 'SalvatorePrototype-619.esp'):
            with self.subTest(name):
                # Structure only: these reference vanilla records outside the small test index.
                result = validate((FIXTURES / 'plugins' / name).read_bytes())
                self.assertEqual(result['errors'], [])

    def test_missing_mesh(self):
        spec = copy.deepcopy(SPEC)
        spec['records']['CoolWorldSalvatore']['model'] = 'salvatore\\nope.nif'
        errors = self.check(self.built(spec))['errors']
        self.assertEqual(errors, ['STAT CoolWorldSalvatore model missing: Data\\meshes\\salvatore\\nope.nif'])

    def test_missing_texture(self):
        (self.data_dir / 'textures' / 'salvatore' / 'front_atlas_m5.dds').unlink()
        errors = self.check(self.built())['errors']
        self.assertEqual(len(errors), 1)
        self.assertIn('texture missing: Data\\textures\\salvatore\\front_atlas_m5.dds', errors[0])

    def test_mesh_found_in_bsa(self):
        spec = copy.deepcopy(SPEC)
        spec['records']['CoolWorldSalvatore']['model'] = 'Dungeons\\Facility\\Room\\FacRmFloor01.nif'
        self.assertEqual(self.check(self.built(spec))['errors'], [])

    def test_wrong_hedr_count(self):
        plugin = codec.parse(self.built())
        hedr = bytearray(plugin.header.get('HEDR'))
        struct.pack_into('<I', hedr, 4, 18)
        plugin.header.subrecords = [codec.Subrecord(s.tag, bytes(hedr) if s.tag == 'HEDR' else s.data)
                                    for s in plugin.header.subrecords]
        errors = self.check(codec.write(plugin), assets=False)['errors']
        self.assertEqual(errors, ['header: HEDR record count 18, file has 25 records+groups'])

    def test_cell_in_wrong_block(self):
        plugin = codec.parse(self.built())
        plugin.top_group('CELL').children[0].label = struct.pack('<i', 3)
        errors = self.check(codec.write(plugin), assets=False)['errors']
        self.assertTrue(any('belongs in block 9 sub-block 4' in e for e in errors), errors)

    def test_reference_to_unknown_master_record(self):
        plugin = codec.parse(self.built())
        cell_refs = plugin.top_group('CELL').children[0].children[0].children[1].children[0].children
        ref = cell_refs[-1]
        ref.subrecords = [codec.Subrecord('NAME', struct.pack('<I', 0x00099999)) if s.tag == 'NAME' else s
                          for s in ref.subrecords]
        errors = self.check(codec.write(plugin), assets=False)['errors']
        self.assertEqual(errors, ['REFR %08X base 00099999 not found in FalloutNV.esm index' % ref.form_id])

    def test_duplicate_formid(self):
        plugin = codec.parse(self.built())
        lights = plugin.top_group('LIGH').children
        lights[1].form_id = lights[0].form_id
        errors = self.check(codec.write(plugin), assets=False)['errors']
        self.assertTrue(any(e.startswith('duplicate FormID') for e in errors), errors)

    def test_truncated_file(self):
        result = self.check(self.built()[:-5])
        self.assertFalse(result['ok'])
        self.assertTrue(result['errors'][0].startswith('structure:'))


class AssetTests(unittest.TestCase):
    def test_nif_texture_scan(self):
        self.assertEqual(nif_textures(NIF), ['textures\\salvatore\\front_atlas_m5.dds'])
        with self.assertRaises(AssetError):
            nif_textures(b'DDS garbage')

    def test_bsa_round_trip_and_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.bsa'
            make_bsa(path, {'meshes\\a\\b.nif': b'1', 'meshes\\a\\c.nif': b'2', 'textures\\t.dds': b'3'})
            self.assertEqual(bsa_names(path), {'meshes\\a\\b.nif', 'meshes\\a\\c.nif', 'textures\\t.dds'})
            (Path(tmp) / 'bad.bsa').write_bytes(b'NOPE' + b'\0' * 40)
            with self.assertRaises(AssetError):
                bsa_names(Path(tmp) / 'bad.bsa')


if __name__ == '__main__':
    unittest.main()
