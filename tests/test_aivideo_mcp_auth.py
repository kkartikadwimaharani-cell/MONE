import importlib
import os
import unittest


class AivideoMcpBearerAuthTests(unittest.TestCase):
    """Covers the MII_MCP_API_KEY Bearer-token path added for the MiiAiVideo
    MCP server: a second, non-cookie way into /api/aivideo/* endpoints,
    plus /api/aivideo/capabilities which the MCP server's list_models tool
    depends on."""

    def setUp(self):
        os.environ['MII_AIVIDEO_PASSWORD'] = 'browser-password'
        os.environ['MII_MCP_API_KEY'] = 'mcp-secret-key-xyz'
        import app as app_module
        importlib.reload(app_module)
        self.app = app_module
        self.client = app_module.app.test_client()

    def tearDown(self):
        os.environ.pop('MII_AIVIDEO_PASSWORD', None)
        os.environ.pop('MII_MCP_API_KEY', None)

    def bearer(self, key):
        return {'Authorization': f'Bearer {key}'} if key is not None else {}

    def test_no_credentials_are_rejected(self):
        resp = self.client.get('/api/aivideo/capabilities')
        self.assertEqual(resp.status_code, 401)

    def test_wrong_bearer_key_is_rejected(self):
        resp = self.client.get('/api/aivideo/capabilities', headers=self.bearer('not-the-key'))
        self.assertEqual(resp.status_code, 401)

    def test_correct_bearer_key_is_accepted_and_returns_model_data(self):
        resp = self.client.get('/api/aivideo/capabilities', headers=self.bearer('mcp-secret-key-xyz'))
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()['data']
        self.assertIn('models', data)
        self.assertIn('counts', data)
        self.assertEqual(sum(data['counts'].values()), len(data['models']))
        self.assertGreaterEqual(sum(data['counts'].values()), 116)
        slugs={model['slug'] for model in data['models']}
        self.assertIn('seedance-2.5', slugs)
        self.assertIn('wan-3.0-video-prime', slugs)
        self.assertTrue(all(model.get('handler') and model.get('available')
                            for model in data['models']))

    def test_bearer_auth_is_exempt_from_csrf_check_on_post_routes(self):
        # A browser session would need a matching X-CSRF-Token header on any
        # POST here; a Bearer caller must NOT be blocked by that check (it
        # isn't cookie-based, so it can't be a CSRF victim in the first
        # place). We only assert the response isn't the CSRF 403 — the
        # route may still fail for other reasons (missing provider keys),
        # which is fine and unrelated to what this test covers.
        resp = self.client.post('/api/aivideo/enhance', json={'prompt': 'x'}, headers=self.bearer('mcp-secret-key-xyz'))
        self.assertNotEqual(resp.status_code, 403)

    def test_missing_bearer_still_hits_csrf_guard_for_session_auth(self):
        # Sanity check the exemption is scoped to Bearer auth only — a
        # logged-in *session* with no CSRF header must still be blocked,
        # same as before this change.
        with self.client.session_transaction() as sess:
            sess['mii_aivideo_auth'] = True
        resp = self.client.post('/api/aivideo/enhance', json={'prompt': 'x'})
        self.assertEqual(resp.status_code, 403)

    def test_unset_mcp_key_disables_bearer_path_entirely(self):
        os.environ.pop('MII_MCP_API_KEY', None)
        importlib.reload(self.app)
        client = self.app.app.test_client()
        resp = client.get('/api/aivideo/capabilities', headers=self.bearer('anything'))
        self.assertEqual(resp.status_code, 401)


if __name__ == '__main__':
    unittest.main()
