import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from geck_mcp_nv import geck
from geck_mcp_nv.config import GeckConfig
from geck_mcp_nv.esp import PluginFormatError, fields, validate, walk


def sub(sig, data):
    return sig + struct.pack('<H', len(data)) + data


def record(sig, body=b'', form=0, flags=0):
    return sig + struct.pack('<IIIIHH', len(body), flags, form, 0, 15, 0) + body


def group(body, label=0x100, kind=6):
    return b'GRUP' + struct.pack('<IIiIHH', len(body) + 24, label, kind, 0, 0, 0) + body


def ref(form=0x1001, flags=0):
    return record(b'REFR', sub(b'NAME', struct.pack('<I', 0x20)) +
                  sub(b'DATA', struct.pack('<6f', 1, 2, 3, .25, .5, 1)), form, flags)


def plugin(body=None):
    body = group(group(ref(), kind=9)) if body is None else body
    # Count all records and groups except TES4.
    header = record(b'TES4', sub(b'HEDR', struct.pack('<fII', .94, 0, 0x1002)))
    count = len(list(walk(header + body))) - 1
    return record(b'TES4', sub(b'HEDR', struct.pack('<fII', .94, count, 0x1002))) + body


class PluginEditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = GeckConfig(root, root/'GECK.exe', root/'nvse_loader.exe',
                                 root, root/'backups', root/'screenshots', root/'plugins.txt')
        self.path = root/'test.esp'
        self.path.write_bytes(plugin())
        self.processes = patch.object(geck, 'list_geck_processes', return_value=[])
        self.processes.start()
        self.addCleanup(self.processes.stop)

    def test_fake_signatures_in_unknown_record_are_not_records(self):
        self.path.write_bytes(plugin(record(b'SCPT', ref(0x777) + group(b''), 0x10) + group(ref())))
        refs = geck.esp_list_placed_refs(self.config, self.path.name)['refs']
        self.assertEqual([r['form_id'] for r in refs], ['00001001'])

    def test_move_preserves_rotation_and_unrelated_bytes(self):
        before = self.path.read_bytes()
        result = geck.esp_patch_ref_position(self.config, self.path.name, '1001', 10, 20, 30)
        self.assertEqual(result['before']['rotation'], result['after']['rotation'])
        self.assertEqual(result['after']['position'], {'x':10, 'y':20, 'z':30})
        self.assertEqual(Path(result['backup']).read_bytes(), before)
        changed = [i for i, (a,b) in enumerate(zip(before, self.path.read_bytes())) if a != b]
        data_offset = next(value for sig,value,length in fields(before, result['before']['record_offset'], result['before']['record_size']) if sig == b'DATA')
        self.assertTrue(all(data_offset <= i < data_offset+12 for i in changed))

    def test_partial_rotation_override(self):
        result = geck.esp_patch_ref_position(self.config, self.path.name, '1001', 1, 2, 3, rot_z=2)
        self.assertEqual(result['after']['rotation'], {'x':.25, 'y':.5, 'z':2})

    def test_invalid_coordinates_do_not_write(self):
        before = self.path.read_bytes()
        for invalid in (float('nan'), float('inf'), 1e100):
            with self.assertRaises((geck.GeckAutomationError, OverflowError)):
                geck.esp_patch_ref_position(self.config, self.path.name, '1001', invalid, 2, 3)
            self.assertEqual(self.path.read_bytes(), before)

    def test_open_editor_blocks_mutation(self):
        before = self.path.read_bytes()
        with patch.object(geck, 'list_geck_processes', return_value=[{'name':'GECK.exe'}]):
            with self.assertRaises(geck.GeckAutomationError):
                geck.esp_patch_ref_position(self.config, self.path.name, '1001', 10, 20, 30)
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_lengths_and_truncation(self):
        good = plugin()
        for bad in (good[:-1], good + b'garbage', b'', good[:42] + b'GRUP' + struct.pack('<I', 2) + bytes(16)):
            with self.subTest(size=len(bad)), self.assertRaises(PluginFormatError):
                validate(bad)

    def test_unsupported_records_fail_without_writing(self):
        for body in (group(ref(flags=0x40000)), group(record(b'REFR', sub(b'XXXX', struct.pack('<I', 100)), 0x1001))):
            original = plugin(body)
            self.path.write_bytes(original)
            with self.assertRaises(PluginFormatError):
                geck.esp_patch_ref_position(self.config, self.path.name, '1001', 10, 20, 30)
            self.assertEqual(self.path.read_bytes(), original)

    def test_duplicate_form_id_rejected(self):
        with self.assertRaises(PluginFormatError):
            validate(plugin(group(ref() + ref())))

    def test_delete_updates_nested_groups_and_header(self):
        self.path.write_bytes(plugin(group(group(ref()+ref(0x1002), kind=9))))
        original = self.path.read_bytes()
        geck.esp_delete_refs(self.config, self.path.name, ['1001'])
        updated = self.path.read_bytes()
        validate(updated)
        self.assertEqual(len(original)-len(updated), len(ref()))
        self.assertEqual(struct.unpack_from('<I', updated, 34)[0], 3)
        self.assertEqual([r['form_id'] for r in geck.esp_list_placed_refs(self.config, self.path.name)['refs']], ['00001002'])

    def test_missing_delete_target_is_all_or_nothing(self):
        original = self.path.read_bytes()
        with self.assertRaises(geck.GeckAutomationError):
            geck.esp_delete_refs(self.config, self.path.name, ['1001', 'dead'])
        self.assertEqual(self.path.read_bytes(), original)

    def test_external_change_is_preserved(self):
        original = self.path.read_bytes()
        newer = plugin(group(ref(0x1002)))
        self.path.write_bytes(newer)
        with self.assertRaises(geck.GeckAutomationError):
            geck._atomic_plugin_write(self.config, self.path, original, original)
        self.assertEqual(self.path.read_bytes(), newer)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_failed_replace_leaves_original_and_cleans_temp(self):
        original = self.path.read_bytes()
        with patch.object(geck.os, 'replace', side_effect=OSError('sharing violation')):
            with self.assertRaises(OSError):
                geck.esp_patch_ref_position(self.config, self.path.name, '1001', 10,20,30)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_cell_scoping(self):
        self.path.write_bytes(plugin(group(ref(), label=0x100) + group(ref(0x1002), label=0x200)))
        result = geck.esp_find_nearby_refs(self.config, self.path.name, 1,2,3, cell_form_id='100')
        self.assertEqual([r['form_id'] for r in result['matches']], ['00001001'])
        with patch.object(geck, 'status_bar', return_value={'position':{'x':1,'y':2,'z':3}}):
            report = geck.placement_report(self.config, self.path.name, cell_form_id='200')
        self.assertEqual([r['form_id'] for r in report['refs']], ['00001002'])
        with self.assertRaises(geck.GeckAutomationError):
            geck.placement_report(self.config, self.path.name)

    def test_rollback_restores_exact_bytes(self):
        original = self.path.read_bytes()
        tx = geck.transaction_begin(self.config, self.path.name)
        geck.esp_patch_ref_position(self.config, self.path.name, '1001', 10,20,30)
        geck.transaction_rollback(self.config, self.path.name, tx['transaction_id'])
        self.assertEqual(self.path.read_bytes(), original)

    def test_save_does_not_claim_success_from_title_alone(self):
        active = {'plugin':self.path.name, 'title':'GECK [test.esp]'}
        with patch.object(geck, 'active_plugin', return_value=active), patch.object(geck, '_resolve_window', return_value=Mock()):
            result = geck.save_active_plugin(self.config, wait_seconds=0)
        self.assertFalse(result['saved'])
        self.assertTrue(Path(result['backup']).exists())

    def test_save_requires_changed_stable_file(self):
        active = {'plugin':self.path.name, 'title':'GECK [test.esp]'}
        window = Mock()
        window.menu_select.side_effect = lambda _: self.path.write_bytes(plugin(group(ref()+ref(0x1002))))
        with patch.object(geck, 'active_plugin', return_value=active), patch.object(geck, '_resolve_window', return_value=window):
            result = geck.save_active_plugin(self.config, wait_seconds=2)
        self.assertTrue(result['saved'])

    def test_status_bar_legacy_tool_only_captures_arguments(self):
        original = self.path.read_bytes()
        with patch.object(geck, 'status_bar', return_value={'position':{'x':10,'y':20,'z':30}}):
            result = geck.esp_patch_ref_to_status_bar_offset(self.config, self.path.name, '1001', offset_z=5)
        self.assertFalse(result['applied'])
        self.assertEqual(result['arguments']['z'], 35)
        self.assertEqual(result['arguments']['rot_z'], 1)
        self.assertEqual(self.path.read_bytes(), original)

    def test_duplicate_data_rejected(self):
        self.path.write_bytes(plugin(group(record(b'REFR', sub(b'DATA', struct.pack('<6f', *range(6)))*2, 0x1001))))
        original = self.path.read_bytes()
        with self.assertRaises(geck.GeckAutomationError):
            geck.esp_patch_ref_position(self.config, self.path.name, '1001', 1,2,3)
        self.assertEqual(self.path.read_bytes(), original)

    def test_save_with_modal_dialog_is_unverified(self):
        active = {'plugin':self.path.name, 'title':'GECK [test.esp]'}
        window = Mock()
        window.is_enabled.return_value = False
        window.menu_select.side_effect = lambda _: self.path.write_bytes(plugin(group(ref()+ref(0x1002))))
        with patch.object(geck, 'active_plugin', return_value=active), patch.object(geck, '_resolve_window', return_value=window):
            result = geck.save_active_plugin(self.config, wait_seconds=1)
        self.assertFalse(result['saved'])


if __name__ == '__main__':
    unittest.main()
