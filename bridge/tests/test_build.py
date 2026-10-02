"""Spec -> plugin build tests: reproducibility, stable FormIDs, structure, errors."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from geck_mcp.esp import build, codec, diff
from geck_mcp.esp.formids import FormIdMap, MasterIndex
from geck_mcp.esp.records import SpecError

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / 'fixtures' / 'plugins'
# Frozen copy of the original 13-reference CoolWorld spec; the live project spec keeps evolving.
SPEC = json.loads((Path(__file__).parent / 'fixtures' / 'coolworld.spec.json').read_text())


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        with gzip.open(root / 'FalloutNV.esm.json.gz', 'wt') as s:
            json.dump({'master': 'FalloutNV.esm', 'entries': {
                'FacRmFloor01': ['STAT', '00018EE1', None, 'Dungeons\\Facility\\Room\\FacRmFloor01.nif'],
                'Varmint': ['WEAP', '000E3778', 'Varmint Rifle', None],
                'Fiend1GunCMNV': ['NPC_', '000F1C1B', 'Fiend', None],
                'CrGecko': ['CREA', '00012345', 'Gecko', None],
                'Barrel02Fire256': ['LIGH', '0001DD62', None, 'Clutter\\Barrel02fireLight.NIF'],
                'FXFireLP': ['SOUN', '00015083', None, None]}}, s)
        self.index = MasterIndex([root / 'FalloutNV.esm.json.gz'])
        self.map_path = root / 'formids.json'

    def tearDown(self):
        self.tmp.cleanup()

    def fresh_map(self, adopt=True):
        m = FormIdMap(self.map_path, 'CoolWorld.esp')
        if adopt:
            build.adopt_existing(m, SPEC, (FIXTURES / 'CoolWorld.esp').read_bytes())
        return m

    def test_rebuild_of_hand_built_coolworld_differs_only_by_known_fixes(self):
        data, receipt = build.build(SPEC, self.fresh_map(), self.index)
        changes = diff.diff((FIXTURES / 'CoolWorld.esp').read_bytes(), data)
        summary = sorted((d['record'], tuple(sorted(c['subrecord'] for c in d['changes']))) for d in changes)
        self.assertEqual(summary, [
            ('CELL 01000801', ('XCLW', 'XNAM')),                     # GECK "no water" defaults
            ('LIGH 01000802', ('FMAM', 'FNAM', 'OBND')),             # fade tag fix, light-marker bounds
            ('LIGH 01000803', ('FMAM', 'FNAM', 'OBND')),
            ('LIGH 01000804', ('FMAM', 'FNAM', 'OBND')),
            ('STAT 01000800', ('BRUS',)),                            # GECK default passthrough sound
            ('TES4 00000000', ('CNAM', 'HEDR', 'SNAM')),             # author, true count, marker
        ])
        self.assertEqual(receipt['hedrCount'], 25)
        self.assertEqual(receipt['recordCounts'], {'TES4': 1, 'LIGH': 3, 'STAT': 1, 'CELL': 1, 'REFR': 13})

    def test_matches_what_geck_itself_saved(self):
        # GECK re-saved the installed CoolWorld.esp on 2026-09-29 (evidence/oracle/). Our spec build
        # must equal it except for author/description text and GECK's own next-object-ID counter.
        geck = (FIXTURES / 'CoolWorld-geck-saved.esp').read_bytes()
        data, _ = build.build(SPEC, self.fresh_map(), self.index)
        changes = diff.diff(geck, data)
        self.assertEqual([d['record'] for d in changes], ['TES4 00000000'])
        header = {c['subrecord']: c for c in changes[0]['changes']}
        self.assertEqual(sorted(header), ['CNAM', 'HEDR', 'SNAM'])
        a, b = bytes.fromhex(header['HEDR']['a']), bytes.fromhex(header['HEDR']['b'])
        self.assertEqual(a[:8], b[:8])            # version and record count agree; only next-ID differs

    def test_reproducible_bytes(self):
        a, _ = build.build(SPEC, self.fresh_map(), self.index)
        m = self.fresh_map()
        m.save()
        b, _ = build.build(SPEC, FormIdMap(self.map_path, 'CoolWorld.esp'), self.index)
        self.assertEqual(a, b)

    def test_hedr_count_matches_structure(self):
        data, receipt = build.build(SPEC, self.fresh_map(), self.index)
        plugin = codec.parse(data)
        groups = records = 0
        def walk(items):
            nonlocal groups, records
            for item in items:
                if isinstance(item, codec.Group):
                    groups += 1
                    walk(item.children)
                else:
                    records += 1
        walk(plugin.groups)
        hedr_count = int.from_bytes(plugin.header.get('HEDR')[4:8], 'little')
        self.assertEqual(hedr_count, groups + records)
        self.assertEqual(int.from_bytes(plugin.header.get('HEDR')[8:12], 'little'), 0x81D)

    def test_adding_an_object_keeps_every_existing_formid(self):
        m = self.fresh_map()
        _, before = build.build(SPEC, m, self.index)
        spec = copy.deepcopy(SPEC)
        spec['cells']['CoolWorld']['objects'].insert(1, {'ref_id': 'extra', 'base': '@FacRmFloor01',
                                                          'position': [0, 0, 300]})
        _, after = build.build(spec, m, self.index)
        for key, form in before['formIds'].items():
            self.assertEqual(after['formIds'][key], form)
        self.assertEqual(after['formIds']['REFR:CoolWorld:extra'], '0100081D')

    def test_removed_object_is_retired(self):
        m = self.fresh_map()
        build.build(SPEC, m, self.index)
        spec = copy.deepcopy(SPEC)
        spec['cells']['CoolWorld']['objects'] = [o for o in spec['cells']['CoolWorld']['objects']
                                                 if o['ref_id'] != 'floor.c']
        spec['cells']['CoolWorld']['objects'].append({'ref_id': 'new', 'base': '@FacRmFloor01'})
        _, receipt = build.build(spec, m, self.index)
        self.assertEqual(receipt['formIds']['REFR:CoolWorld:new'], '0100081D')   # 0x818 not reused
        self.assertIn('REFR:CoolWorld:floor.c', m.retired)

    def test_interior_block_rule_matches_geck(self):
        # GECK stored SalvatoreTestCell (local 0x1375 = 4981) in block 1, sub-block 8.
        self.assertEqual(build.interior_block(0x1375), (1, 8))
        data, _ = build.build(SPEC, self.fresh_map(), self.index)
        cells = [(r, p) for r, p in codec.parse(data).records() if r.type == 'CELL']
        self.assertEqual([g.label_text for g in cells[0][1]], ['CELL', '9', '4'])   # 0x801 = 2049

    def test_actors_are_placed_as_achr_and_acre(self):
        spec = copy.deepcopy(SPEC)
        objects = spec['cells']['CoolWorld']['objects']
        objects += [{'ref_id': 'fiend', 'base': '@Fiend1GunCMNV', 'position': [0, -200, 0]},
                    {'ref_id': 'gecko', 'base': '@CrGecko'},
                    {'ref_id': 'barrel.l', 'base': '@Barrel02Fire256', 'position': [-140, 0, 0]}]
        data, receipt = build.build(spec, self.fresh_map(), self.index)
        kinds = {r['refId']: r['recordType'] for r in receipt['references']['CoolWorld']}
        self.assertEqual((kinds['fiend'], kinds['gecko'], kinds['barrel.l'], kinds['salvatore']),
                         ('ACHR', 'ACRE', 'REFR', 'REFR'))
        placed = [r for r, _ in codec.parse(data).records() if r.type in ('ACHR', 'ACRE')]
        self.assertEqual(sorted(r.type for r in placed), ['ACHR', 'ACRE'])
        from geck_mcp.esp.validate import validate
        self.assertEqual(validate(data, self.index)['errors'], [])

    def test_unplaceable_base_is_rejected(self):
        spec = copy.deepcopy(SPEC)
        spec['cells']['CoolWorld']['objects'].append({'ref_id': 'snd', 'base': '@FXFireLP'})
        with self.assertRaises(SpecError) as caught:
            build.build(spec, self.fresh_map(), self.index)
        self.assertIn('SOUN record cannot be placed', str(caught.exception))

    def test_validator_rejects_npc_placed_as_refr(self):
        spec = copy.deepcopy(SPEC)
        spec['cells']['CoolWorld']['objects'].append({'ref_id': 'fiend', 'base': '@Fiend1GunCMNV'})
        data, _ = build.build(spec, self.fresh_map(), self.index)
        plugin = codec.parse(data)
        for rec, _ in plugin.records():
            if rec.type == 'ACHR':
                rec.type = 'REFR'
        from geck_mcp.esp.validate import validate
        errors = validate(codec.write(plugin), self.index)['errors']
        self.assertTrue(any('places a NPC_; that must be a ACHR record' in e for e in errors), errors)

    def test_switching_stat_to_mstt_keeps_the_formid(self):
        m = self.fresh_map()
        _, before = build.build(SPEC, m, self.index)
        spec = copy.deepcopy(SPEC)
        spec['records']['CoolWorldSalvatore']['type'] = 'MSTT'
        data, after = build.build(spec, m, self.index)
        self.assertEqual(after['formIds'], before['formIds'])
        self.assertEqual(after['recordCounts'].get('MSTT'), 1)
        self.assertNotIn('STAT', after['recordCounts'])
        types = [g.label for g in codec.parse(data).groups]
        self.assertEqual(types, [b'LIGH', b'MSTT', b'CELL'])      # GECK's top-group order
        from geck_mcp.esp.validate import validate
        self.assertEqual(validate(data, self.index)['errors'], [])

    def test_generated_marker(self):
        data, _ = build.build(SPEC, self.fresh_map(), self.index)
        self.assertTrue(build.is_generated(data, 'coolworld'))
        self.assertFalse(build.is_generated(data, 'other'))
        self.assertFalse(build.is_generated((FIXTURES / 'CoolWorld.esp').read_bytes()))

    def test_errors_name_the_problem(self):
        def broken(mutate):
            spec = copy.deepcopy(SPEC)
            mutate(spec)
            return spec
        cases = [
            (lambda s: s['cells']['CoolWorld']['objects'][0].update(base='@Nowhere'), 'objects[0].base'),
            (lambda s: s['cells']['CoolWorld']['objects'][0].update(base='@Varmint'), None),
            (lambda s: s['records'].update(FacRmFloor01={'type': 'STAT', 'model': 'a.nif'}), 'already exists in FalloutNV.esm'),
            (lambda s: s['records'].update(CoolWorld={'type': 'STAT', 'model': 'a.nif'}), 'also used in'),
            (lambda s: s['cells']['CoolWorld']['objects'][1].update(ref_id='salvatore'), 'duplicate ref_id'),
            (lambda s: s['records']['CoolWorldSalvatore'].update(type='NPC_'), 'records.CoolWorldSalvatore.type'),
            (lambda s: s.update(plugin='../evil.esp'), 'plugin'),
            (lambda s: s.update(extra=1), 'unknown top-level'),
        ]
        for mutate, fragment in cases:
            spec = broken(mutate)
            if fragment is None:
                # Placing a weapon base in a cell is allowed structurally (REFR of WEAP is valid).
                build.build(spec, FormIdMap(self.map_path, 'CoolWorld.esp'), self.index)
                continue
            with self.subTest(fragment=fragment), self.assertRaises(SpecError) as caught:
                build.build(spec, FormIdMap(self.map_path, 'CoolWorld.esp'), self.index)
            self.assertIn(fragment, str(caught.exception))


if __name__ == '__main__':
    unittest.main()
