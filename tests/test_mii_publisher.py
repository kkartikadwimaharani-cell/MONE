import tempfile
import unittest
import uuid
import json
from urllib.parse import parse_qs, urlparse

import mii_publisher
import mii_publisher_instagram


class FakeSecrets:
    def __init__(self):
        self.values = {}

    def get(self, key, default=''):
        return self.values.get(key, default)

    def set(self, key, value):
        if value:
            self.values[key] = value
        else:
            self.values.pop(key, None)

    def delete(self, key):
        self.values.pop(key, None)


class FakeLogger:
    def warning(self, *args, **kwargs):
        pass


def config_getter(store):
    config = {
        'INSTAGRAM_APP_ID': 'app-id',
        'INSTAGRAM_APP_SECRET': 'server-only-app-secret',
        'INSTAGRAM_REDIRECT_URI': 'https://connect.example.com/mii-publisher/instagram/callback',
        'INSTAGRAM_GRAPH_VERSION': 'v26.0',
    }

    def get(name, default=''):
        return config.get(name, store.get(name, default))

    return get


class RecordingInstagramService(mii_publisher_instagram.InstagramPublisherService):
    def __init__(self, directory):
        self.fake_secrets = FakeSecrets()
        self.fake_secrets.set('INSTAGRAM_ACCESS_TOKEN', 'server-only-token')
        self.fake_secrets.set('INSTAGRAM_USER_ID', 'ig-user-1')
        self.fake_secrets.set('INSTAGRAM_USERNAME', 'mii')
        super().__init__(directory, self.fake_secrets, config_getter(self.fake_secrets), FakeLogger())
        self.calls = []

    def _graph_request(self, method, path, *, token=None, correlation_id=None, **kwargs):
        self.calls.append({'method': method, 'path': path, 'kwargs': kwargs})
        if path == 'me':
            return {'user_id': 'ig-user-1', 'username': 'mii', 'account_type': 'BUSINESS', 'media_count': 7}
        if method == 'POST' and path == 'ig-user-1/media':
            return {'id': 'container-1'}
        if method == 'GET' and path == 'container-1':
            return {'status_code': 'FINISHED', 'status': 'Finished'}
        if method == 'POST' and path == 'ig-user-1/media_publish':
            return {'id': 'published-media-1'}
        raise AssertionError(f'Unexpected Instagram call: {method} {path}')


class FakeResponse:
    def __init__(self, status_code, body, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body


class OAuthHttp:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({'method': method, 'url': url, 'kwargs': kwargs})
        if url == mii_publisher_instagram.INSTAGRAM_TOKEN_URL:
            return FakeResponse(200, {'access_token': 'short-token', 'user_id': 'ig-user-1'})
        if url == f'{mii_publisher_instagram.INSTAGRAM_GRAPH_HOST}/access_token':
            return FakeResponse(200, {'access_token': 'long-token', 'expires_in': 5184000})
        if url.endswith('/me'):
            return FakeResponse(200, {
                'user_id': 'ig-user-1', 'username': 'mii',
                'account_type': 'BUSINESS', 'media_count': 1,
            })
        raise AssertionError(f'Unexpected request: {method} {url}')


class MiiPublisherInstagramTests(unittest.TestCase):
    def test_publisher_device_views_are_deduplicated_and_raw_id_is_not_stored(self):
        with tempfile.TemporaryDirectory() as directory:
            store = mii_publisher.PublisherStore(directory)
            first = str(uuid.uuid4())
            second = str(uuid.uuid4())
            self.assertEqual(store.record_lock_visit(first), 1)
            self.assertEqual(store.record_lock_visit(first), 1)
            self.assertEqual(store.record_lock_visit(second), 2)
            self.assertEqual(store.record_lock_visit('invalid-device-id'), 2)
            with open(store.path, 'r', encoding='utf-8') as handle:
                saved = json.load(handle)
            self.assertNotIn(first, repr(saved))
            self.assertNotIn(second, repr(saved))
            self.assertEqual(len(saved['lock_visits']), 2)

    def test_direct_reel_url_validation_without_vps_download(self):
        video = mii_publisher.validate_instagram_video_url('https://cdn.example.com/media/reel.mp4?signature=temporary')
        self.assertEqual(video['type'], 'video')
        self.assertEqual(video['destination'], 'instagram_reels')
        self.assertEqual(video['transport'], 'direct_remote_url')

    def test_unsafe_preview_or_non_video_media_is_rejected(self):
        invalid = [
            'http://cdn.example.com/reel.mp4',
            'https://127.0.0.1/reel.mp4',
            'https://10.0.0.4/reel.mp4',
            'https://www.dropbox.com/scl/fi/example/reel.mp4?dl=0',
            'https://cdn.example.com/image.jpg',
            'https://cdn.example.com/not-a-media-file',
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(mii_publisher.PublisherMediaError):
                mii_publisher.validate_instagram_video_url(url)

    def test_missing_environment_degrades_without_crashing(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FakeSecrets()
            service = mii_publisher_instagram.InstagramPublisherService(
                directory, store, lambda name, default='': default, FakeLogger())
            status = service.connection_status()
            self.assertFalse(status['configured'])
            self.assertFalse(status['connected'])
            self.assertEqual(status['health']['status'], 'CONFIGURATION ERROR')
            self.assertIn('INSTAGRAM_APP_ID', status['missing_configuration'])

    def test_configured_without_token_requires_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FakeSecrets()
            service = mii_publisher_instagram.InstagramPublisherService(
                directory, store, config_getter(store), FakeLogger())
            status = service.connection_status()
            self.assertTrue(status['configured'])
            self.assertFalse(status['connected'])
            self.assertEqual(status['health']['status'], 'AUTHORIZATION REQUIRED')

    def test_authorization_url_uses_official_scopes_and_hides_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FakeSecrets()
            service = mii_publisher_instagram.InstagramPublisherService(
                directory, store, config_getter(store), FakeLogger())
            url = service.authorization_url('secure-state', reconnect=True)
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            self.assertEqual(parsed.netloc, 'www.instagram.com')
            self.assertEqual(query['state'], ['secure-state'])
            self.assertIn('instagram_business_basic', query['scope'][0])
            self.assertIn('instagram_business_content_publish', query['scope'][0])
            self.assertNotIn('server-only-app-secret', url)

    def test_oauth_callback_exchange_stores_only_long_lived_token_server_side(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FakeSecrets()
            http = OAuthHttp()
            service = mii_publisher_instagram.InstagramPublisherService(
                directory, store, config_getter(store), FakeLogger(), http=http)
            profile = service.exchange_code('single-use-code')
            self.assertEqual(profile['username'], 'mii')
            self.assertEqual(store.get('INSTAGRAM_ACCESS_TOKEN'), 'long-token')
            self.assertNotEqual(store.get('INSTAGRAM_ACCESS_TOKEN'), 'short-token')
            self.assertTrue(store.get('INSTAGRAM_TOKEN_EXPIRES_AT'))
            self.assertTrue(all('server-only-app-secret' not in call['url'] for call in http.calls))

    def test_disconnect_removes_all_instagram_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RecordingInstagramService(directory)
            service.disconnect()
            for key in mii_publisher_instagram.TOKEN_KEYS:
                self.assertFalse(service.fake_secrets.get(key))
            self.assertEqual(service.connection_status()['health']['status'], 'AUTHORIZATION REQUIRED')

    def test_publish_waits_for_real_provider_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RecordingInstagramService(directory)
            payload = {
                'confirmed': True,
                'idempotency_key': str(uuid.uuid4()),
                'media_url': 'https://cdn.example.com/media/reel.mp4',
                'caption': 'MII Reel',
            }
            created = service.create_reel(payload)
            self.assertTrue(created['ok'])
            self.assertEqual(created['job']['status'], 'PROCESSING')
            self.assertFalse(created['job']['provider_media_id'])
            self.assertFalse(any(call['path'].endswith('/media_publish') for call in service.calls))

            published = service.refresh_publish_status(created['job']['id'])
            self.assertEqual(published['status'], 'PUBLISHED')
            self.assertEqual(published['provider_media_id'], 'published-media-1')
            publish_calls = [call for call in service.calls if call['path'].endswith('/media_publish')]
            self.assertEqual(len(publish_calls), 1)

            duplicate = service.create_reel(payload)
            self.assertTrue(duplicate['duplicate_prevented'])
            self.assertEqual(len([call for call in service.calls if call['path'] == 'ig-user-1/media']), 1)

    def test_provider_errors_are_classified_without_secret_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FakeSecrets()
            service = mii_publisher_instagram.InstagramPublisherService(
                directory, store, config_getter(store), FakeLogger())
            auth = service._provider_error(FakeResponse(400, {'error': {'code': 190, 'message': 'Invalid token'}}), 'req-1')
            rate = service._provider_error(FakeResponse(429, {'error': {'code': 4}}, {'Retry-After': '30'}), 'req-2')
            self.assertIsInstance(auth, mii_publisher.PublisherAuthError)
            self.assertEqual(auth.health_status, 'AUTHORIZATION REQUIRED')
            self.assertIsInstance(rate, mii_publisher.PublisherRateLimitError)
            self.assertEqual(rate.retry_after, 30)
            self.assertNotIn('server-only-app-secret', repr(auth.public_detail()))

    def test_connection_status_never_returns_access_token(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RecordingInstagramService(directory)
            status = service.connection_status()
            self.assertTrue(status['connected'])
            self.assertNotIn('server-only-token', repr(status))
            self.assertNotIn('access_token', repr(status).lower())


if __name__ == '__main__':
    unittest.main()
