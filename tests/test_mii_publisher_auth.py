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
            json={'url': 'https://cdn.example.com/image.jpg'},
            headers={'X-CSRF-Token': 'ai-token'},
        )
        self.assertEqual(wrong.status_code, 403)
        correct = self.client.post(
            '/api/mii-publisher/media/validate',
            json={'url': 'https://cdn.example.com/image.jpg'},
            headers={'X-CSRF-Token': 'publisher-token'},
        )
        self.assertEqual(correct.status_code, 200)


if __name__ == '__main__':
    unittest.main()
