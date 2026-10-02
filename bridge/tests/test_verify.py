"""Receipt vs Cell View matching (tier 3), independent of GECK's column layout."""
import unittest

from geck_mcp.verify import match_cell_references

RECEIPT = {'references': {'CoolWorld': [
    {'refId': 'salvatore', 'formId': '01000810', 'base': '01000800', 'baseSpec': '@CoolWorldSalvatore'},
    {'refId': 'floor.c', 'formId': '01000818', 'base': '00018EE1', 'baseSpec': '@FacRmFloor01'},
]}}


class MatchTests(unittest.TestCase):
    def test_match_by_formid_and_base_name(self):
        shown = {'columns': ['Editor ID', 'Form ID', 'Base'], 'rows': [
            ['', '01000810', 'CoolWorldSalvatore'], ['', '01000818', 'FacRmFloor01']]}
        result = match_cell_references(RECEIPT, 'CoolWorld', shown)
        self.assertTrue(result['ok'], result)

    def test_real_geck_cell_view_rows(self):
        # Captured live from GECK 2026-09-29: active-plugin records carry a ' *' suffix.
        shown = {'columns': ['Editor ID', 'Form ID', 'Type', 'Ownership', 'Lock Level'], 'rows': [
            ['CoolWorldSalvatore *', '01000810', 'Static', '', ''],
            ['FacRmFloor01 *', '01000818', 'Static', '', '']]}
        self.assertTrue(match_cell_references(RECEIPT, 'CoolWorld', shown)['ok'])

    def test_short_hex_and_base_by_formid(self):
        shown = {'rows': [['1000810', '1000800'], ['1000818', '18EE1']]}
        self.assertTrue(match_cell_references(RECEIPT, 'CoolWorld', shown)['ok'])

    def test_missing_extra_and_wrong_base(self):
        shown = {'rows': [['01000810', 'SomethingElse'], ['01000999', 'X']]}
        result = match_cell_references(RECEIPT, 'CoolWorld', shown)
        self.assertFalse(result['ok'])
        self.assertEqual(result['missing'], ['01000818'])
        self.assertEqual(len(result['unexpected']), 1)
        self.assertEqual(result['baseMismatches'][0]['formId'], '01000810')


if __name__ == '__main__':
    unittest.main()
