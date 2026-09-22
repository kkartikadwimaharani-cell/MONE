import sys
import tempfile
import types
import unittest
import uuid
from datetime import datetime, timedelta, timezone

try:
    import requests  # noqa: F401
except ImportError:  # Minimal local test shim; Railway installs requests.
    requests = types.ModuleType('requests')
    requests.RequestException = Exception
    requests.post = None
    sys.modules['requests'] = requests

import mii_publisher


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


class RecordingService(mii_publisher.BufferPublisherService):
    def __init__(self, directory):
        store = FakeSecrets()
        store.set('BUFFER_ACCESS_TOKEN', 'server-only-token')
        super().__init__(directory, store, lambda name, default='': store.get(name, default), FakeLogger())
        self.calls = []

    def accounts_and_channels(self):
        return {'organizations': [{'id': 'org-1', 'name': 'MII'}], 'channels': [
            {'id': 'channel-1', 'name': 'MII Instagram', 'platform': 'instagram', 'connected': True},
            {'id': 'channel-2', 'name': 'MII Facebook', 'platform': 'facebook', 'connected': True},
        ]}

    def _graphql(self, query, variables=None, retry_auth=True):
        self.calls.append({'query': query, 'variables': variables})
        channel = variables['input']['channelId']
        return {'createPost': {'post': {'id': f'post-{channel}', 'status': 'sent', 'dueAt': None}}}


class MiiPublisherTests(unittest.TestCase):
    def test_direct_remote_media(self):
        image = mii_publisher.validate_media_url('https://cdn.example.com/media/post.jpg')
        video = mii_publisher.validate_media_url('https://files.example.com/reel.mp4?rlkey=public')
        self.assertEqual(image['type'], 'image')
        self.assertEqual(video['type'], 'video')
        self.assertEqual(video['transport'], 'direct_remote_url')

    def test_unsafe_or_non_direct_media_is_rejected(self):
        invalid = [
            'http://cdn.example.com/post.jpg', 'https://127.0.0.1/post.jpg',
            'https://10.0.0.4/post.mp4', 'https://www.dropbox.com/scl/fi/example/post.mp4?dl=0',
            'https://cdn.example.com/post.mp4?x-amz-signature=secret',
            'https://cdn.example.com/not-a-media-file',
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(mii_publisher.PublisherValidationError):
                mii_publisher.validate_media_url(url)

    def test_schedule_validation(self):
        future = datetime.now(timezone.utc) + timedelta(hours=4)
        due_at = mii_publisher.parse_schedule(future.strftime('%Y-%m-%d'), future.strftime('%H:%M'), 'UTC')
        self.assertTrue(due_at.endswith('Z'))
        with self.assertRaises(mii_publisher.PublisherValidationError):
            mii_publisher.parse_schedule('2020-01-01', '10:00', 'UTC')

    def test_history_blocks_duplicate_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            store = mii_publisher.PublisherHistoryStore(directory)
            key = str(uuid.uuid4())
            self.assertEqual(store.begin(key, 'hash'), (None, False))
            store.complete(key, 'hash', {'ok': True}, [{'status': 'PUBLISHED'}])
            result, duplicate = store.begin(key, 'hash')
            self.assertTrue(duplicate)
            self.assertEqual(result, {'ok': True})

    def test_publish_sends_direct_url_to_each_selected_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RecordingService(directory)
            payload = {
                'confirmed': True, 'idempotency_key': str(uuid.uuid4()),
                'media_url': 'https://cdn.example.com/media/post.mp4', 'caption': 'MII post',
                'channel_ids': ['channel-1', 'channel-2'], 'mode': 'now',
            }
            result = service.publish(payload)
            self.assertTrue(result['ok'])
            self.assertEqual(len(service.calls), 2)
            for call in service.calls:
                self.assertEqual(call['variables']['input']['mode'], 'shareNow')
                self.assertEqual(call['variables']['input']['assets'], [
                    {'video': {'url': 'https://cdn.example.com/media/post.mp4'}}
                ])
            again = service.publish(payload)
            self.assertTrue(again['duplicate_prevented'])
            self.assertEqual(len(service.calls), 2)

    def test_connection_status_never_returns_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RecordingService(directory)
            status = service.connection_status()
            self.assertTrue(status['connected'])
            self.assertNotIn('token', status)
            self.assertNotIn('server-only-token', repr(status))


if __name__ == '__main__':
    unittest.main()
