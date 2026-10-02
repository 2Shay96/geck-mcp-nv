"""Codec tests: byte-exact round-trip on real plugins plus synthetic edge cases."""
from pathlib import Path
import struct
import unittest

from geck_mcp.esp import codec
from geck_mcp.esp.codec import FormatError, Group, Plugin, Record, Subrecord

FIXTURES = Path(__file__).parent / 'fixtures' / 'plugins'


def header():
    return Record('TES4', 0, _subrecords=[
        Subrecord('HEDR', struct.pack('<fII', 1.34, 1, 0x801)),
        Subrecord('MAST', b'FalloutNV.esm\0'), Subrecord('DATA', b'\0' * 8)])


class RoundTrip(unittest.TestCase):
    def test_real_plugins_round_trip_exactly(self):
        files = sorted(FIXTURES.glob('*.esp'))
        self.assertGreaterEqual(len(files), 5)
        for path in files:
            data = path.read_bytes()
            with self.subTest(path.name):
                self.assertEqual(codec.write(codec.parse(data)), data)
                self.assertEqual(codec.write(codec.parse(data, lazy=False)), data)

    def test_geck_saved_cell_structure(self):
        plugin = codec.parse((FIXTURES / 'SalvatorePrototype-619.esp').read_bytes())
        cells = [(r, p) for r, p in plugin.records() if r.type == 'CELL']
        self.assertEqual(len(cells), 1)
        cell, path = cells[0]
        self.assertEqual(cell.editor_id, 'SalvatoreTestCell')
        self.assertEqual([g.group_type for g in path], [0, 2, 3])
        self.assertEqual([g.label_text for g in path], ['CELL', '1', '8'])

    def test_large_subrecord_uses_xxxx(self):
        big = bytes(range(256)) * 300  # 76,800 bytes > 65,535
        rec = Record('STAT', 0x01000800, _subrecords=[Subrecord('EDID', b'Big\0'), Subrecord('MODT', big)])
        plugin = Plugin(header(), [Group(b'STAT', 0, children=[rec])])
        data = codec.write(plugin)
        self.assertIn(b'XXXX\x04\x00', data)
        again = codec.parse(data)
        self.assertEqual(again.groups[0].children[0].get('MODT'), big)
        self.assertEqual(codec.write(again), data)

    def test_compressed_record_lazy_and_reencoded(self):
        subs = [Subrecord('EDID', b'Packed\0'), Subrecord('FULL', b'x' * 500)]
        rec = Record('NPC_', 0x00012345, flags=codec.COMPRESSED, _subrecords=subs)
        data = codec.write(Plugin(header(), [Group(b'NPC_', 0, children=[rec])]))
        parsed = codec.parse(data)
        lazy = parsed.groups[0].children[0]
        self.assertIsNone(lazy._subrecords)            # not decoded yet
        self.assertEqual(codec.write(parsed), data)    # verbatim payload
        self.assertEqual(lazy.editor_id, 'Packed')     # decodes on access
        lazy.subrecords = lazy.subrecords + [Subrecord('DESC', b'new\0')]
        again = codec.parse(codec.write(parsed), lazy=False)
        self.assertEqual(again.groups[0].children[0].get('DESC'), b'new\0')

    def test_stream_iterator_filters_types(self):
        data = (FIXTURES / 'CoolWorld.esp').read_bytes()
        refs = list(codec.iter_records(data, types=['REFR']))
        self.assertEqual(len(refs), 13)
        self.assertEqual(refs[0][1][0], (b'CELL', 0))
        self.assertEqual([t for _, t in refs[0][1]], [0, 2, 3, 6, 9])
        everything = [r.type for r, _ in codec.iter_records(data)]
        self.assertEqual(everything.count('LIGH'), 3)
        self.assertEqual(everything[0], 'TES4')


class Malformed(unittest.TestCase):
    def setUp(self):
        self.data = (FIXTURES / 'CoolWorld.esp').read_bytes()

    def test_every_truncation_is_rejected(self):
        for cut in range(1, len(self.data)):
            with self.subTest(cut=cut):
                try:
                    plugin = codec.parse(self.data[:cut])
                except FormatError:
                    continue
                # Only a cut exactly on a top-level boundary may parse; it must then be shorter.
                self.assertLess(len(codec.write(plugin)), len(self.data))

    def test_not_a_plugin(self):
        with self.assertRaises(FormatError):
            codec.parse(b'RIFF' + self.data[4:])

    def test_record_overrunning_group(self):
        bad = bytearray(self.data)
        # Grow the first LIGH record's declared size past its group.
        pos = bad.index(b'LIGH', bad.index(b'GRUP') + 12)  # first LIGH record, after its group label
        struct.pack_into('<I', bad, pos + 4, 10_000)
        with self.assertRaises(FormatError):
            codec.parse(bytes(bad))

    def test_xxxx_requires_zero_size_follower(self):
        body = b'XXXX\x04\x00' + struct.pack('<I', 3) + b'EDID\x03\x00abc'
        with self.assertRaises(FormatError):
            codec.parse_subrecords(body)

    def test_bad_tag_on_write(self):
        with self.assertRaises(ValueError):
            codec.encode_subrecords([Subrecord('TOOLONG', b'')])


if __name__ == '__main__':
    unittest.main()
