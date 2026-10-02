"""FormID allocator and reference resolver tests."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from geck_mcp.esp.formids import FIRST_LOCAL, FormIdError, FormIdMap, MasterIndex, Resolver


def write_index(folder, master, entries):
    path = Path(folder) / (master + '.json.gz')
    with gzip.open(path, 'wt', encoding='utf-8') as stream:
        json.dump({'master': master, 'entries': entries}, stream)
    return path


class Allocator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'formids' / 'coolworld.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_keys_in_spec_order_from_0x800(self):
        ids = FormIdMap(self.path, 'CoolWorld.esp').sync(['B', 'A', 'C'])
        self.assertEqual(ids, {'B': 0x800, 'A': 0x801, 'C': 0x802})

    def test_ids_survive_reorder_insert_and_reload(self):
        first = FormIdMap(self.path, 'CoolWorld.esp')
        before = first.sync(['Stat', 'Cell', 'Light'])
        first.save()
        again = FormIdMap(self.path, 'CoolWorld.esp')
        after = again.sync(['NewThing', 'Light', 'Cell', 'Stat'])
        for key in before:
            self.assertEqual(after[key], before[key])
        self.assertEqual(after['NewThing'], 0x803)
        self.assertEqual(again.next_object_id, 0x804)

    def test_removed_keys_are_retired_not_reused_and_revive(self):
        m = FormIdMap(self.path, 'CoolWorld.esp')
        m.sync(['A', 'B'])
        m.sync(['A'])                       # B retired
        ids = m.sync(['A', 'C'])            # C must not take B's ID
        self.assertEqual(ids['C'], 0x802)
        self.assertEqual(m.sync(['A', 'B', 'C'])['B'], 0x801)

    def test_seed_adopts_existing_ids(self):
        m = FormIdMap(self.path, 'CoolWorld.esp')
        m.seed('CoolWorldSalvatore', 0x800)
        m.seed('REFR:CoolWorld:salvatore', 0x810)
        ids = m.sync(['CoolWorldSalvatore', 'REFR:CoolWorld:salvatore', 'Extra'])
        self.assertEqual(ids['Extra'], 0x811)
        with self.assertRaises(FormIdError):
            m.seed('Other', 0x800)
        with self.assertRaises(FormIdError):
            m.seed('Low', 0x10)

    def test_duplicate_keys_and_wrong_plugin(self):
        m = FormIdMap(self.path, 'CoolWorld.esp')
        with self.assertRaises(FormIdError):
            m.sync(['A', 'A'])
        m.sync(['A'])
        m.save()
        with self.assertRaises(FormIdError):
            FormIdMap(self.path, 'Other.esp')

    def test_saved_file_is_deterministic(self):
        m = FormIdMap(self.path, 'CoolWorld.esp')
        m.sync(['A', 'B'])
        m.save()
        first = self.path.read_bytes()
        m2 = FormIdMap(self.path, 'CoolWorld.esp')
        m2.sync(['A', 'B'])
        m2.save()
        self.assertEqual(self.path.read_bytes(), first)


class Resolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.index = MasterIndex([
            write_index(self.tmp.name, 'FalloutNV.esm', {
                'FacRmFloor01': ['STAT', '00018EE1', None, 'Dungeons\\Facility\\Room\\FacRmFloor01.nif'],
                'Varmint': ['WEAP', '000E3778', 'Varmint Rifle', None]}),
            write_index(self.tmp.name, 'DeadMoney.esm', {
                'DMFloor': ['STAT', '01001234', None, 'dm\\floor.nif']})])
        self.own = {'CoolWorldSalvatore': 0x01000800}

    def tearDown(self):
        self.tmp.cleanup()

    def test_own_and_master_editor_ids(self):
        r = Resolver(['FalloutNV.esm'], self.own, self.index)
        self.assertEqual(r.resolve('@CoolWorldSalvatore'), 0x01000800)
        self.assertEqual(r.resolve('@facrmfloor01'), 0x00018EE1)   # case-insensitive
        self.assertEqual(r.resolve('00018EE1'), 0x00018EE1)

    def test_type_expectation(self):
        r = Resolver(['FalloutNV.esm'], self.own, self.index)
        with self.assertRaises(FormIdError) as caught:
            r.resolve('@Varmint', expect_types=['STAT'])
        self.assertIn('WEAP', str(caught.exception))

    def test_master_not_in_our_mast_list_is_invisible(self):
        r = Resolver(['FalloutNV.esm'], self.own, self.index)
        with self.assertRaises(FormIdError):
            r.resolve('@DMFloor')

    def test_second_master_is_renumbered_to_our_load_order(self):
        r = Resolver(['FalloutNV.esm', 'DeadMoney.esm'], {'Mine': 0x02000800}, self.index)
        self.assertEqual(r.resolve('@DMFloor'), 0x01001234)
        self.assertEqual(r.resolve('@Mine'), 0x02000800)

    def test_bad_raw_ids(self):
        r = Resolver(['FalloutNV.esm'], self.own, self.index)
        for bad in ['02000001', '01000999', 'xyz', '', None, '18EE1']:
            with self.subTest(bad=bad), self.assertRaises(FormIdError):
                r.resolve(bad)

    def test_unresolved_names_the_masters(self):
        r = Resolver(['FalloutNV.esm'], self.own, self.index)
        with self.assertRaises(FormIdError) as caught:
            r.resolve('@Nope')
        self.assertIn('FalloutNV.esm', str(caught.exception))

    def test_search(self):
        rows = self.index.search('floor', record_type='STAT')
        self.assertEqual([r['editorId'] for r in rows], ['DMFloor', 'FacRmFloor01'])


if __name__ == '__main__':
    unittest.main()
