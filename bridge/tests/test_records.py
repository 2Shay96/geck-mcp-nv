"""Golden-bytes tests: builders must reproduce records GECK wrote itself."""
from pathlib import Path
import struct
import unittest

from geck_mcp.esp import codec, records
from geck_mcp.esp.records import SpecError

FIXTURES = Path(__file__).parent / 'fixtures' / 'plugins'


def geck_plugin():
    return codec.parse((FIXTURES / 'SalvatorePrototype-619.esp').read_bytes())


def find(plugin, rtype, form_id):
    for rec, _ in plugin.records():
        if rec.type == rtype and rec.form_id == form_id:
            return rec
    raise AssertionError('missing %s %08X' % (rtype, form_id))


class GoldenGeckRecords(unittest.TestCase):
    """Records from SalvatorePrototype.esp as saved by GECK (619-byte version)."""

    def setUp(self):
        self.plugin = geck_plugin()

    def assertSameRecord(self, built, original):
        self.assertEqual(codec.encode_record(built).hex(), codec.encode_record(original).hex())

    def test_header(self):
        built = records.tes4(['FalloutNV.esm'], record_count=10, next_object_id=0x1378)
        self.assertSameRecord(built, self.plugin.header)

    def test_stat(self):
        original = find(self.plugin, 'STAT', 0x01000ADD)
        built = records.stat(0x01000ADD, 'SalvatoreStatic', {
            'type': 'STAT', 'model': codec.cstring(original.get('MODL')),
            'bounds': [-64, -64, 64, 64, 64, 64]})
        self.assertSameRecord(built, original)

    def test_interior_cell_with_geck_defaults(self):
        original = find(self.plugin, 'CELL', 0x01001375)
        built = records.cell_interior(0x01001375, 'SalvatoreTestCell', {}, vc1=original.vc1)
        self.assertSameRecord(built, original)

    def test_references(self):
        for form_id in (0x01001376, 0x01001377):
            original = find(self.plugin, 'REFR', form_id)
            pos = list(struct.unpack('<3f', original.get('DATA')[:12]))
            base = struct.unpack('<I', original.get('NAME'))[0]
            built = records.refr(form_id, base, {'position': pos}, 'objects', vc1=original.vc1)
            self.assertSameRecord(built, original)


class GoldenVanillaRecords(unittest.TestCase):
    """Records copied from FalloutNV.esm (read by the runner, 2026-09-29)."""

    def test_vanilla_light(self):
        # NVTopsWarmAmbRoom13th 00175B6C
        expected = bytes.fromhex(
            'ffffffffc2010000f0944f00000000000000803f0000b4420000000000000000')
        built = records.ligh(0x00175B6C, 'NVTopsWarmAmbRoom13th', {
            'type': 'LIGH', 'radius': 450, 'color': [240, 148, 79], 'fade': 0.9,
            'bounds': [-38, -40, -74, 38, 40, 48]})
        self.assertEqual(built.get('DATA'), expected)
        self.assertEqual(built.get('FNAM').hex(), '6666663f')
        self.assertEqual(built.get('OBND').hex(), 'daffd8ffb6ff260028003000')
        self.assertEqual([s.tag for s in built.subrecords], ['EDID', 'OBND', 'DATA', 'FNAM'])

    def test_vanilla_static_layout(self):
        built = records.stat(0x0017B7B5, 'NVGuardTower01a', {
            'model': 'architecture\\NCR\\NVGuardTower01a.NIF', 'bounds': [155, -296, -23, 283, 42, 170]})
        self.assertEqual(built.get('OBND').hex(), '9b00d8fee9ff1b012a00aa00')
        self.assertEqual([s.tag for s in built.subrecords], ['EDID', 'OBND', 'MODL', 'BRUS'])


class GoldenMoveableStatic(unittest.TestCase):
    def test_vanilla_mstt_layout(self):
        # FXFireSmall01 00070587 in FalloutNV.esm: EDID, OBND, MODL, DATA 00 (+ SNAM sound, not built yet)
        built = records.mstt(0x00070587, 'FXFireSmall01', {
            'type': 'MSTT', 'model': 'Effects\\Ambient\\FXFireSmall01.NIF', 'bounds': [-47, -45, -33, 38, 45, 64]})
        self.assertEqual([s.tag for s in built.subrecords], ['EDID', 'OBND', 'MODL', 'DATA'])
        self.assertEqual(built.get('OBND').hex(), 'd1ffd3ffdfff26002d004000')
        self.assertEqual(built.get('DATA'), b'\0')
        with self.assertRaises(SpecError):
            records.mstt(1, 'M', {'model': 'a.nif', 'sound': '@X'})


class Validation(unittest.TestCase):
    def test_bad_inputs_name_the_field(self):
        cases = [
            (lambda: records.stat(1, 'Bad Name', {'model': 'a.nif'}), 'records.Bad Name'),
            (lambda: records.stat(1, 'S', {'model': 'meshes\\a.nif'}), '.model'),
            (lambda: records.stat(1, 'S', {'model': '..\\a.nif'}), '.model'),
            (lambda: records.stat(1, 'S', {'model': 'C:\\a.nif'}), '.model'),
            (lambda: records.stat(1, 'S', {'model': 'a.dds'}), '.model'),
            (lambda: records.stat(1, 'S', {'model': 'a.nif', 'bounds': [1, 0, 0, 0, 0, 0]}), '.bounds'),
            (lambda: records.stat(1, 'S', {'model': 'a.nif', 'colour': 1}), 'unknown STAT'),
            (lambda: records.ligh(1, 'L', {'color': [300, 0, 0]}), '.color[0]'),
            (lambda: records.ligh(1, 'L', {'flags': ['strobe']}), 'unknown flag'),
            (lambda: records.ligh(1, 'L', {'radius': 1.5}), '.radius'),
            (lambda: records.cell_interior(1, 'C', {'lighting': {'fog_far': float('nan')}}), '.fog_far'),
            (lambda: records.refr(1, 2, {'scale': 50}, 'cells.C.objects[0]'), '.scale'),
            (lambda: records.refr(1, 2, {'position': [0, 0]}, 'cells.C.objects[0]'), '.position'),
            (lambda: records.tes4([], 0, 0x800), 'masters'),
        ]
        for build, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(SpecError) as caught:
                build()
            self.assertIn(fragment, str(caught.exception))

    def test_explicit_lighting_is_not_inherited(self):
        cell = records.cell_interior(1, 'C', {'lighting': {'ambient': [20, 20, 28], 'fog_far': 10000}})
        inherit = struct.unpack('<I', cell.get('LNAM'))[0]
        self.assertFalse(inherit & records.LIGHTING_INHERIT['ambient'])
        self.assertFalse(inherit & records.LIGHTING_INHERIT['fog_far'])
        self.assertTrue(inherit & records.LIGHTING_INHERIT['directional'])
        self.assertEqual(cell.get('XCLL')[:4], bytes((20, 20, 28, 0)))

    def test_rotation_degrees_to_radians(self):
        ref = records.refr(1, 2, {'rotation': [0, 0, 90]}, 'o')
        self.assertAlmostEqual(struct.unpack('<6f', ref.get('DATA'))[5], 1.5707963, places=6)


if __name__ == '__main__':
    unittest.main()
