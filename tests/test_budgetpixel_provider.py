import unittest
from unittest.mock import Mock

import budgetpixel_provider as provider


class BudgetPixelProviderTests(unittest.TestCase):
    def test_all_model_mappings(self):
        expected_video = {
            ('seedance', 'MINI'): '/videos/seedance-2.0-mini',
            ('seedance', 'FAST'): '/videos/seedance-2.0-fast',
            ('seedance', 'PRO'): '/videos/seedance-2.0',
            ('seedance25', 'STANDARD'): '/videos/seedance-2.5',
            ('wan30', 'STANDARD'): '/videos/wan-3.0-video',
            ('wan30', 'PRIME'): '/videos/wan-3.0-video-prime',
        }
        expected_image = {
            ('flux2', 'KLEIN'): '/images/flux-2-klein',
            ('qwenbp', 'STANDARD'): '/images/qwen-image',
            ('flux2', 'PRO'): '/images/flux-2-pro',
            ('flux2', 'DEV'): '/images/flux-2-dev',
            ('seedream5', 'LITE'): '/images/seedream-5.0-lite',
            ('seedream5', 'PRO'): '/images/seedream-5.0-pro',
            ('klingimage', 'V3'): '/images/kling-v3',
            ('klingimage', 'OMNI'): '/images/kling-v3-omni',
            ('gptimage', 'LOW'): '/images/gpt-image-2',
            ('gptimage', 'STANDARD'): '/images/gpt-image-2',
            ('gptimage', 'HIGH'): '/images/gpt-image-2',
        }
        self.assertEqual(provider.VIDEO_MODELS, expected_video)
        self.assertEqual(provider.IMAGE_MODELS, expected_image)

    def test_submit_uses_backend_bearer_and_job_id(self):
        response = Mock(status_code=200)
        response.json.return_value = {'job_id': 'job-1'}
        session = Mock(post=Mock(return_value=response))
        result = provider.submit_image('flux2', 'KLEIN', {'prompt': 'cat'}, 'secret', session=session)
        self.assertEqual(result['job_id'], 'job-1')
        kwargs = session.post.call_args.kwargs
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer secret')

    def test_status_normalization(self):
        for raw, normalized in [('pending', 'queued'), ('starting', 'processing'),
                                ('processing', 'processing'), ('completing', 'processing'),
                                ('succeeded', 'completed'), ('failed', 'failed'), ('timeout', 'failed')]:
            self.assertEqual(provider.normalize_result({'status': raw})['status'], normalized)
        result = provider.normalize_result({'status': 'succeeded', 'result': {'image_url': 'https://cdn/x.png'}})
        self.assertEqual(result['url'], 'https://cdn/x.png')

    def test_poll_pending_processing_succeeded(self):
        responses = []
        for status, result in [('pending', None), ('processing', None),
                               ('succeeded', {'video_url': 'https://cdn/x.mp4'})]:
            response = Mock(status_code=200)
            response.json.return_value = {'status': status, 'result': result}
            responses.append(response)
        session = Mock(get=Mock(side_effect=responses))
        result = provider.poll('job-1', 'secret', session=session, interval=0, sleep=lambda _: None)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['url'], 'https://cdn/x.mp4')
        self.assertTrue(all(call.args[0].endswith('/videos/job-1') for call in session.get.call_args_list))

    def test_image_poll_and_multi_image_normalization(self):
        response = Mock(status_code=200)
        response.json.return_value = {'status': 'succeeded', 'images': [
            {'url': 'https://cdn/one.png'}, 'https://cdn/two.png']}
        session = Mock(get=Mock(return_value=response))
        result = provider.poll('image-1', 'secret', kind='image', session=session,
                               interval=0, sleep=lambda _: None)
        self.assertEqual(result['url'], 'https://cdn/one.png')
        self.assertEqual(len(result['images']), 2)
        self.assertTrue(session.get.call_args.args[0].endswith('/images/image-1'))

    def test_poll_failed_and_timeout(self):
        failed = Mock(status_code=200)
        failed.json.return_value = {'status': 'failed'}
        self.assertEqual(provider.poll('job-1', 'secret', session=Mock(get=Mock(return_value=failed)),
                                       interval=0, sleep=lambda _: None)['status'], 'failed')
        with self.assertRaises(provider.ProviderError):
            provider.poll('job-1', 'secret', session=Mock(), timeout_seconds=0, sleep=lambda _: None)

    def test_http_errors_and_malformed_responses_are_sanitized(self):
        for status in (400, 401, 422, 429, 500):
            response = Mock(status_code=status, text='raw provider secret')
            response.json.return_value = {'error': 'raw provider secret'}
            err = provider.normalize_error(response)
            self.assertNotIn('raw provider secret', err.public_message)
        response = Mock(status_code=200)
        response.json.side_effect = ValueError('bad json')
        with self.assertRaises(provider.ProviderError):
            provider.submit_video('seedance', 'MINI', {'prompt': 'x'}, 'key', session=Mock(post=Mock(return_value=response)))


if __name__ == '__main__':
    unittest.main()
