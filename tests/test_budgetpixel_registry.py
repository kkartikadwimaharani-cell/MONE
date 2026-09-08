import unittest
from unittest.mock import Mock

import budgetpixel_provider as provider
import budgetpixel_registry as registry


class BudgetPixelRegistryTests(unittest.TestCase):
    def setUp(self):
        registry.reset_cache()

    def response(self, payload):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    def test_catalog_parsing_marks_reviewed_and_unknown_separately(self):
        session = Mock(get=Mock(return_value=self.response({'data': [
            {'slug': 'seedance-2.5', 'name': 'Seedance 2.5', 'type': 'video'},
            {'slug': 'future-music', 'name': 'Future Music', 'type': 'music'},
        ]})))
        data = registry.get_registry('secret', session=session, force=True)
        known = registry.model_by_slug('seedance-2.5', data)
        unknown = registry.model_by_slug('future-music', data)
        self.assertTrue(known['available'])
        self.assertEqual(known['status'], 'UNVERIFIED')
        self.assertFalse(unknown['available'])
        self.assertEqual(unknown['status'], 'UNSUPPORTED')
        self.assertNotIn('secret', repr(data))

    def test_cache_and_safe_fallback(self):
        session = Mock()
        session.get.side_effect = RuntimeError('offline')
        first = registry.get_registry('key', session=session, ttl=60)
        second = registry.get_registry('key', session=session, ttl=60)
        self.assertEqual(session.get.call_count, 1)
        self.assertTrue(first['models'])
        self.assertEqual(first, second)
        self.assertIn('RuntimeError', first['sync_error'])

    def test_grouped_catalog_and_categories(self):
        parsed = registry._remote_rows({'models': {'audios': [{'id': 'voice-one'}],
                                                    'images': [{'model': 'image-one'}]}})
        self.assertEqual([(x['slug'], x['category']) for x in parsed],
                         [('voice-one', 'audio'), ('image-one', 'image')])

    def test_generic_endpoint_allowlist(self):
        data = registry.get_registry('', force=True)
        response = Mock(status_code=200)
        response.json.return_value = {'id': 'job'}
        session = Mock(post=Mock(return_value=response))
        provider.submit_model('seedance-2.5', 'video', {'prompt': 'x'}, 'key', data, session=session)
        self.assertTrue(session.post.call_args.args[0].endswith('/v1/videos/seedance-2.5'))
        with self.assertRaises(provider.ProviderError):
            provider.submit_model('seedance-2.5', 'audio', {'prompt': 'x'}, 'key', data, session=session)
        with self.assertRaises(provider.ProviderError):
            provider.submit_model('../account/credits', 'video', {}, 'key', data, session=session)

    def test_audio_result_normalization(self):
        result = provider.normalize_result({'status': 'succeeded',
                                            'output': {'audio_url': 'https://cdn/x.wav'}})
        self.assertEqual(result['url'], 'https://cdn/x.wav')


if __name__ == '__main__':
    unittest.main()
