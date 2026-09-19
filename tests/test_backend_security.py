import unittest
from unittest.mock import patch

import app
import budgetpixel_provider
import budgetpixel_video_catalog


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

    def test_lock_page_is_private_and_does_not_embed_password(self):
        marker = 'never-render-this-password'
        with patch.object(app, '_mii_aivideo_password', return_value=marker):
            response = self.client.get('/ai-video')
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('MII AI Studio now supports secure MCP and CLI access', html)
        self.assertIn('Back to Home', html)
        self.assertNotIn('Kembali ke Beranda', html)
        self.assertNotIn('&#8594;', html)
        self.assertNotIn(marker, html)
        self.assertNotIn('fonts.googleapis.com', html)
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.assertIn("connect-src 'self'", response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['X-Robots-Tag'], 'noindex, nofollow, noarchive')

    def test_all_seedance_video_contracts_are_capped_at_fifteen_seconds(self):
        for (family, _variant), caps in budgetpixel_provider.VIDEO_CAPABILITIES.items():
            if family.startswith('seedance'):
                self.assertLessEqual(caps['duration'][1], 15)
        for slug, caps in budgetpixel_video_catalog.VIDEO_CATALOG.items():
            if slug.startswith('seedance-') and caps['durations']:
                self.assertLessEqual(max(caps['durations']), 15)
        with self.assertRaises(budgetpixel_provider.ProviderError):
            budgetpixel_provider.build_video_payload(
                'seedance25', 'STANDARD',
                {'duration': 16, 'resolution': '720p', 'aspect_ratio': '16:9'},
                'duration guard',
            )


if __name__ == '__main__':
    unittest.main()
