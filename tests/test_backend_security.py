import unittest
from unittest.mock import patch

import app


class BackendSecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_makima_password_has_no_source_fallback(self):
        with patch.object(app, 'get_secret', return_value=''):
            self.assertEqual(app._get_makima_access_password(), '')
            self.assertFalse(app._is_valid_makima_access_key('known-default'))
            response = self.client.post(
                '/api/makima-access', json={'password': 'known-default'})
            self.assertEqual(response.status_code, 403)

    def test_provider_diagnostics_are_not_public(self):
        with patch.object(app, '_get_gemini_model',
                          side_effect=AssertionError('provider must not run')):
            self.assertEqual(self.client.get('/api/test-env').status_code, 401)
            self.assertIn(self.client.get('/api/test-gemini').status_code, (302, 405))
            self.assertEqual(self.client.post('/api/test-gemini').status_code, 401)

    def test_gemini_diagnostic_requires_csrf_and_never_runs_without_key(self):
        with self.client.session_transaction() as session:
            session['mii_aivideo_auth'] = True
            session['mii_csrf'] = 'test-csrf'
        self.assertEqual(self.client.post('/api/test-gemini').status_code, 403)
        with patch.object(app, 'get_secret', return_value=''), \
             patch.object(app, '_get_gemini_model',
                          side_effect=AssertionError('provider must not run')):
            response = self.client.post(
                '/api/test-gemini',
                headers={'X-CSRF-Token': 'test-csrf'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['configured'])


if __name__ == '__main__':
    unittest.main()
