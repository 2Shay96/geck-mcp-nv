import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from geck_mcp_nv.config import default_load_order_file, get_config
from geck_mcp_nv.server import mcp


class ConfigurationTests(unittest.TestCase):
    def test_explicit_game_path_and_profile_override(self):
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp) / 'Game'
            profile = Path(temp) / 'Profile' / 'plugins.txt'
            with patch.dict(os.environ, {'GECK_MCP_FNV_DIR': str(game),
                                         'GECK_MCP_LOAD_ORDER_FILE': str(profile)}, clear=True):
                config = get_config()
            self.assertEqual(config.game_dir, game)
            self.assertEqual(config.data_dir, game / 'Data')
            self.assertEqual(config.geck_exe, game / 'GECK.exe')
            self.assertEqual(config.load_order_file, profile)

    def test_argument_overrides_environment(self):
        with patch.dict(os.environ, {'GECK_MCP_FNV_DIR': 'environment-game'}, clear=True):
            self.assertEqual(get_config('explicit-game').game_dir, Path('explicit-game'))

    def test_load_order_without_local_app_data_is_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(default_load_order_file())

    def test_mcp_exposes_updated_contract(self):
        tools = asyncio.run(mcp.list_tools())
        schemas = {tool.name: getattr(tool, "inputSchema", None) or tool.input_schema for tool in tools}
        self.assertEqual(len(schemas), 46)
        self.assertIsNone(schemas['geck_esp_patch_ref_position']['properties']['rot_x']['default'])
        self.assertIn('cell_form_id', schemas['geck_placement_report']['properties'])
        self.assertFalse(schemas['geck_placement_plan_from_status_bar']['properties']['use_status_rotation']['default'])


if __name__ == '__main__':
    unittest.main()
