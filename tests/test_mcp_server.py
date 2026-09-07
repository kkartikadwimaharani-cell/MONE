import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from starlette.testclient import TestClient


class McpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'MII_MCP_API_KEY': 'test-only'}):
            cls.server = runpy.run_path(str(Path(__file__).parents[1] / 'mcp-server/server.py'))

    def test_invalid_json_shape(self):
        for payload in ([], None, 'error'):
            response = Mock(status_code=502)
            response.json.return_value = payload
            self.assertIn('error', self.server['_as_json'](response))

    def test_task_id_alias(self):
        response = Mock(status_code=200)
        response.json.return_value = {'id': 'job-123', 'status': 'pending'}
        self.assertEqual(self.server['_as_json'](response)['task_id'], 'job-123')

    def test_mcp_auth_and_initialize(self):
        app = self.server['BearerAuthMiddleware'](self.server['mcp'].streamable_http_app())
        with TestClient(app) as client:
            self.assertEqual(client.post('/mcp', json={}).status_code, 401)
            self.assertEqual(client.post('/mcp', json={}, headers={'Authorization': 'Bearer wrong'}).status_code, 401)
            response = client.post('/mcp', headers={
                'Authorization': 'Bearer test-only',
                'Accept': 'application/json, text/event-stream',
            }, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-03-26', 'capabilities': {},
                'clientInfo': {'name': 'test', 'version': '1.0'},
            }})
            self.assertEqual(response.status_code, 200)
            self.assertIn('MiiAiVideo', response.text)
