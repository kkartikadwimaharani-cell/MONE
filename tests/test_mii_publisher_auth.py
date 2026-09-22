import unittest
from unittest.mock import patch

import app


class MiiPublisherAuthIsolationTests(unittest.TestCase):
    def setUp(self):
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()
        with app._PUBLISHER_UNLOCK_LOCK:
            app._PUBLISHER_UNLOCK_ATTEMPTS.clear()

    def test_publisher_unlock_does_not_unlock_ai_studio(self):
        with patch.object(app, '_mii_publisher_password', return_value='publisher-only'):
            response = self.client.post(
                '/mii-publisher/unlock', json={'password': 'publisher-only'})
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            self.assertTrue(session.get('mii_publisher_auth'))
            self.assertFalse(session.get('mii_aivideo_auth'))
        publisher = self.client.get('/mii-publisher')
        ai_studio = self.client.get('/ai-video')
        self.assertIn('MII PUBLISHER — MII NETWORK', publisher.get_data(as_text=True))
        self.assertIn('MII AI STUDIO | PRIVATE WORKSPACE', ai_studio.get_data(as_text=True))

    def test_ai_studio_session_does_not_unlock_publisher(self):
        with self.client.session_transaction() as session:
            session['mii_aivideo_auth'] = True
        response = self.client.get('/mii-publisher')
        html = response.get_data(as_text=True)
        self.assertIn('MII PUBLISHER | PRIVATE ACCESS', html)
        self.assertIn('SEPARATE FROM MII AI STUDIO', html)
        self.assertNotIn('PUBLISH • SCHEDULE • MANAGE', html)

    def test_publisher_password_is_fail_closed_and_never_rendered(self):
        marker = 'publisher-secret-must-not-render'
        with patch.object(app, '_mii_publisher_password', return_value=marker):
            lock_page = self.client.get('/mii-publisher')
        self.assertNotIn(marker, lock_page.get_data(as_text=True))
        with patch.object(app, '_mii_publisher_password', return_value=''):
            response = self.client.post('/mii-publisher/unlock', json={'password': ''})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()['ok'])

    def test_publisher_api_rejects_ai_studio_session(self):
        with self.client.session_transaction() as session:
            session['mii_aivideo_auth'] = True
            session['mii_csrf'] = 'ai-token'
        response = self.client.get('/api/mii-publisher/status')
        self.assertEqual(response.status_code, 401)

    def test_publisher_csrf_is_separate_from_ai_studio_csrf(self):
        with self.client.session_transaction() as session:
            session['mii_publisher_auth'] = True
            session['mii_publisher_csrf'] = 'publisher-token'
            session['mii_csrf'] = 'ai-token'
        wrong = self.client.post(
            '/api/mii-publisher/media/validate',
            json={'url': 'https://cdn.example.com/reel.mp4'},
            headers={'X-CSRF-Token': 'ai-token'},
        )
        self.assertEqual(wrong.status_code, 403)
        correct = self.client.post(
            '/api/mii-publisher/media/validate',
            json={'url': 'https://cdn.example.com/reel.mp4'},
            headers={'X-CSRF-Token': 'publisher-token'},
        )
        self.assertEqual(correct.status_code, 200)

    def test_missing_instagram_env_does_not_crash_publisher_status(self):
        with self.client.session_transaction() as session:
            session['mii_publisher_auth'] = True
        with patch.object(app._mii_publisher_service, '_secret', return_value=''):
            response = self.client.get('/api/mii-publisher/status')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data['configured'])
        self.assertEqual(data['health']['status'], 'CONFIGURATION ERROR')

    def test_instagram_connect_uses_separate_oauth_state(self):
        with self.client.session_transaction() as session:
            session['mii_publisher_auth'] = True
            session['mii_publisher_csrf'] = 'publisher-token'
        with patch.object(
                app._mii_publisher_service, 'authorization_url',
                return_value='https://www.instagram.com/oauth/authorize?state=safe') as authorize:
            response = self.client.post(
                '/api/mii-publisher/instagram/connect',
                json={'reconnect': True},
                headers={'X-CSRF-Token': 'publisher-token'},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn('instagram.com', response.get_json()['authorization_url'])
        with self.client.session_transaction() as session:
            self.assertIn('mii_publisher_instagram_oauth', session)
            self.assertNotIn('mii_dropbox_oauth_state', session)
        self.assertTrue(authorize.call_args.kwargs['reconnect'])

    def test_instagram_callback_rejects_wrong_state(self):
        with self.client.session_transaction() as session:
            session['mii_publisher_auth'] = True
            session['mii_publisher_instagram_oauth'] = {
                'state': 'expected', 'created_at': __import__('time').time(),
            }
        with patch.object(app._mii_publisher_service, 'exchange_code') as exchange:
            response = self.client.get(
                '/mii-publisher/instagram/callback?state=wrong&code=secret-code')
        self.assertEqual(response.status_code, 302)
        self.assertIn('instagram_error=invalid_oauth_state', response.location)
        exchange.assert_not_called()

    def test_instagram_callback_exchanges_code_after_valid_state(self):
        now = __import__('time').time()
        with self.client.session_transaction() as session:
            session['mii_publisher_auth'] = True
            session['mii_publisher_instagram_oauth'] = {
                'state': 'expected', 'created_at': now,
            }
        with patch.object(app._mii_publisher_service, 'exchange_code', return_value={'username': 'mii'}) as exchange:
            response = self.client.get(
                '/mii-publisher/instagram/callback?state=expected&code=single-use-code')
        self.assertEqual(response.status_code, 302)
        self.assertIn('instagram=connected', response.location)
        exchange.assert_called_once_with('single-use-code')

    def test_instagram_disconnect_is_csrf_protected(self):
        with self.client.session_transaction() as session:
            session['mii_publisher_auth'] = True
            session['mii_publisher_csrf'] = 'publisher-token'
        blocked = self.client.post('/api/mii-publisher/instagram/disconnect', json={})
        self.assertEqual(blocked.status_code, 403)
        with patch.object(app._mii_publisher_service, 'disconnect') as disconnect:
            allowed = self.client.post(
                '/api/mii-publisher/instagram/disconnect', json={},
                headers={'X-CSRF-Token': 'publisher-token'},
            )
        self.assertEqual(allowed.status_code, 200)
        disconnect.assert_called_once()

    def test_publish_status_transition_requires_csrf(self):
        with self.client.session_transaction() as session:
            session['mii_publisher_auth'] = True
            session['mii_publisher_csrf'] = 'publisher-token'
        blocked = self.client.post('/api/mii-publisher/publish/job-1/status', json={})
        self.assertEqual(blocked.status_code, 403)
        with patch.object(
                app._mii_publisher_service, 'refresh_publish_status',
                return_value={'id': 'job-1', 'status': 'PROCESSING'}) as refresh:
            allowed = self.client.post(
                '/api/mii-publisher/publish/job-1/status', json={},
                headers={'X-CSRF-Token': 'publisher-token'},
            )
        self.assertEqual(allowed.status_code, 200)
        refresh.assert_called_once_with('job-1')


if __name__ == '__main__':
    unittest.main()
