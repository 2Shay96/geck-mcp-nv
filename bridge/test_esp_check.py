"""Verifier boundary tests; synthetic bytes are never written to an ESP."""
import struct
import unittest
from esp_check import read_cell_reference, read_model

def field(tag, value):
    return tag + struct.pack('<H', len(value)) + value

def record(tag, body, form_id=0):
    return struct.pack('<4sIIIIHH', tag, len(body), 0, form_id, 0, 15, 0) + body

def fixture():
    stat = record(b'STAT', field(b'EDID', b'SalvatoreStatic\0') + field(b'MODL', b'salvatore\\test.nif\0'), 0x1000ADD)
    group = struct.pack('<4sI4sI8s', b'GRUP', 24 + len(stat), b'STAT', 0, b'\0' * 8) + stat
    return record(b'TES4', b'') + group

def group(label, group_type, body):
    return struct.pack('<4sIII8s', b'GRUP', 24 + len(body), label, group_type, b'\0' * 8) + body

def cell_fixture():
    cell_id, ref_id, base_id = 0x1001375, 0x1001376, 0x1000ADD
    cell = record(b'CELL', field(b'EDID', b'SalvatoreTestCell\0'), cell_id)
    refr = record(b'REFR', field(b'NAME', struct.pack('<I', base_id)) +
                  field(b'DATA', struct.pack('<6f', 1, 2, 3, 0, 0, 0)), ref_id)
    children = group(cell_id, 6, group(cell_id, 9, refr))
    return record(b'TES4', b'') + group(struct.unpack('<I', b'CELL')[0], 0, cell + children)

class VerifierTests(unittest.TestCase):
    def test_exact_record(self):
        result = read_model(fixture(), 'SalvatoreStatic')
        self.assertEqual(result['formId'], '01000ADD')
        self.assertEqual(result['modelPath'], 'salvatore\\test.nif')

    def test_wrong_identity(self):
        with self.assertRaisesRegex(ValueError, 'found 0'):
            read_model(fixture(), 'Salvatore')

    def test_stale_group_length(self):
        data = bytearray(fixture())
        struct.pack_into('<I', data, 28, len(data) - 24 - 10)
        with self.assertRaisesRegex(ValueError, 'enclosing boundary'):
            read_model(data, 'SalvatoreStatic')

    def test_truncated(self):
        with self.assertRaises(ValueError):
            read_model(fixture()[:-1], 'SalvatoreStatic')

    def test_duplicate_identity(self):
        data = fixture()
        with self.assertRaisesRegex(ValueError, 'found 2'):
            read_model(data + data[24:], 'SalvatoreStatic')

    def test_cell_reference(self):
        result = read_cell_reference(cell_fixture(), 'SalvatoreTestCell', 0x1000ADD)
        self.assertEqual(result['cellFormId'], '01001375')
        self.assertEqual(result['reference']['formId'], '01001376')
        self.assertEqual(result['reference']['position'], {'x': 1.0, 'y': 2.0, 'z': 3.0})

if __name__ == '__main__':
    unittest.main()
