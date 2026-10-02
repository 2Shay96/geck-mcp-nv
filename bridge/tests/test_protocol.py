import json
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from geck_mcp.server import make_server
import test_service


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = test_service.ServiceTests()
        self.fixture.setUp()

    async def asyncTearDown(self):
        self.fixture.tearDown()

    async def test_discovery_schemas_errors_resources_and_prompt(self):
        async with Client(make_server(self.fixture.p, self.fixture.service)) as client:
            listing = await client.list_tools()
            tools = listing.tools if hasattr(listing, 'tools') else listing
            by_name = {tool.name: tool for tool in tools}
            self.assertEqual(len(by_name), 24)
            for name in ('geck_actor_photo', 'geck_render_capture', 'geck_image_cutout'):
                self.assertIn(name, by_name)
            self.assertIn('RESUMABLE', by_name['geck_actor_photo'].description)
            self.assertIsNotNone(by_name['geck_status'].output_schema)
            result = await client.call_tool('geck_status', {})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content['data']['sessionId'], '100:123')
            result = await client.call_tool('geck_records_find', {'session_id':'100:123','limit':501})
            self.assertTrue(result.is_error)
            result = await client.call_tool('geck_project_attach', {'session_id':'wrong-session'})
            self.assertTrue(result.is_error)
            resource = await client.read_resource('geck://project/manifest')
            self.assertIn('Fixture.esp', str(resource))
            prompt = await client.get_prompt('update_static_model', {'editor_id':'FixtureStatic','model_path':'fixture\\new.nif'})
            self.assertIn('whole-plugin', str(prompt))

    async def test_real_stdio_process(self):
        path = Path(self.fixture.tmp.name)/'project.json'
        path.write_text(self.fixture.p.model_dump_json())
        root = Path(__file__).resolve().parents[1]
        parameters = StdioServerParameters(command=sys.executable,
                        args=[str(root/'run_mcp.py'),'--project',str(path)], cwd=str(root))
        async with Client(parameters) as client:
            result = await client.call_tool('geck_capabilities', {})
            self.assertFalse(result.is_error)
            self.assertIn('STAT', str(result.structured_content))
            result = await client.call_tool('geck_plugin_validate', {'expected_models':{'FixtureStatic':'fixture\\old.nif'}})
            self.assertFalse(result.is_error, result)
            self.assertTrue(result.structured_content['data']['persistenceVerified'])

    async def test_legacy_initialize_client(self):
        async with Client(make_server(self.fixture.p, self.fixture.service), mode='legacy') as client:
            listing = await client.list_tools()
            tools = listing.tools if hasattr(listing, 'tools') else listing
            self.assertIn('geck_plugin_load', {tool.name for tool in tools})
            result = await client.call_tool('geck_status', {})
            self.assertFalse(result.is_error)
            self.assertTrue(result.structured_content['ok'])


if __name__ == '__main__':
    unittest.main()
