import os
import unittest
from unittest.mock import Mock, patch

import app


class PreApiAuditTests(unittest.TestCase):
    def _capture_generation_body(self, payload):
        captured = {}
        class NoStartThread:
            def __init__(self, target=None, args=(), **kwargs):
                captured['args'] = args
            def start(self):
                pass
        with app.app.test_request_context('/api/aivideo/generate', method='POST', json=payload):
            app.session['mii_aivideo_auth'] = True
            with patch.object(app.threading, 'Thread', NoStartThread), patch.object(app, '_persist_task'):
                response = app.aivideo_generate()
        self.assertEqual(response.status_code, 200)
        return captured['args'][3]

    def test_env_secret_fallback(self):
        with patch.object(app._app_secrets_store, 'get', return_value=''), \
             patch.dict(os.environ, {'BUDGETPIXEL_API_KEY': 'railway-value'}, clear=False):
            self.assertEqual(app.get_secret('BUDGETPIXEL_API_KEY'), 'railway-value')

    def test_public_debug_template_is_provider_neutral_and_mobile_safe(self):
        status = {
            'storage': {'status': 'READY', 'mode': 'CONNECTED', 'archive': 'READY',
                        'auto_refresh': '5 SECONDS', 'detail': 'Storage is ready.', 'checked_at': 'now'},
            'generation': {'status': 'READY', 'api_configuration': 'CONFIGURED',
                           'video_backend': 'READY', 'image_backend': 'READY', 'task_engine': 'READY',
                           'polling': 'READY', 'last_request': 'NONE', 'detail': 'Ready.', 'checked_at': 'now'},
            'pipeline': {'archive': 'READY', 'image_preview': 'READY', 'video_preview': 'READY',
                         'history': 'READY', 'last_save': 'NONE'},
            'motion': {'status': 'READY'},
            'request_log': {'status': 'INTERNAL ONLY', 'total': 0, 'errors': 0},
        }
        with app.app.app_context():
            html = app.render_template('ai-video-debug.html', **status)
        forbidden = ('dropbox', 'segmind', 'budgetpixel', 'derabox', 'api_key', 'bearer',
                     'invalid_grant', 'refresh token', 'traceback')
        lower = html.lower()
        for value in forbidden:
            self.assertNotIn(value, lower)
        for width in (360, 390, 412, 430):
            self.assertGreaterEqual(width, 360)
            self.assertIn('@media(max-width:590px)', html)
        self.assertIn('NEXT SCAN', html)
        self.assertIn('REQUEST LOG SUMMARY', html)

    def test_gpt_image_contract_and_video_length_field(self):
        body = self._capture_generation_body({'family': 'gptimage', 'model': 'HIGH', 'prompt': 'x',
            'quality': 'high', 'resolution': '4K', 'num_images': 4, 'output_format': 'jpeg',
            'aspect_ratio': '16:9', 'image_urls': ['https://cdn.example.com/r.png']})
        self.assertEqual(body, {'prompt': 'x', 'quality': 'high', 'resolution': '4K',
            'aspect_ratio': '16:9', 'num_images': 4, 'output_format': 'jpeg',
            'reference_images': ['https://cdn.example.com/r.png']})
        self.assertNotIn('size', body)
        self.assertNotIn('image_urls', body)
        for family, model, seconds in (('seedance25', 'STANDARD', 30), ('wan30', 'PRIME', 22)):
            video = self._capture_generation_body({'family': family, 'model': model,
                                                    'prompt': 'x', 'duration': seconds})
            self.assertEqual(video['length_seconds'], seconds)
            self.assertNotIn('duration', video)

    def test_budgetpixel_video_uses_filtered_prompt_and_preserves_original(self):
        captured = {}

        class NoStartThread:
            def __init__(self, target=None, args=(), **kwargs):
                captured['task_id'], captured['body'] = args[0], args[3]
            def start(self):
                pass

        payload = {'family': 'wan30', 'model': 'PRIME', 'prompt': 'A woman walks home.',
                   'duration': 5}
        with app.app.test_request_context('/api/aivideo/generate', method='POST', json=payload):
            app.session['mii_aivideo_auth'] = True
            with patch.object(app.threading, 'Thread', NoStartThread), patch.object(app, '_persist_task'), \
                    patch.object(app.mii_quality_filter, 'build_final_prompt', return_value='filtered prompt'):
                response = app.aivideo_generate()
        self.assertEqual(response.status_code, 200)
        task = app.AIVIDEO_TASKS.pop(captured['task_id'])
        self.assertEqual(captured['body']['prompt'], 'filtered prompt')
        self.assertEqual(task['request_metadata']['original_prompt'], 'A woman walks home.')
        self.assertEqual(task['request_metadata']['final_prompt'], 'filtered prompt')

    def test_quality_filter_failure_falls_back_to_original_prompt(self):
        with patch.object(app.mii_quality_filter, 'build_final_prompt', side_effect=RuntimeError('filter failed')):
            body = self._capture_generation_body(
                {'family': 'wan30', 'model': 'PRIME', 'prompt': 'Keep this exact prompt.', 'duration': 5}
            )
        self.assertEqual(body['prompt'], 'Keep this exact prompt.')

    def test_generation_creates_persistent_diagnostic_with_reference_trace(self):
        reference_url = 'https://cdn.example.com/reference.png'
        app._aivideo_debug_append_upload({'filename': 'reference.png', 'url': reference_url,
                                          'ok': True, 'at': '2026-09-02T00:00:00Z'})
        captured = {}

        class NoStartThread:
            def __init__(self, target=None, args=(), **kwargs):
                captured['task_id'] = args[0]
            def start(self):
                pass

        payload = {'family': 'gptimage', 'model': 'HIGH', 'prompt': 'exact prompt',
                   'resolution': '4K', 'num_images': 4, 'output_format': 'jpeg',
                   'aspect_ratio': '16:9', 'image_urls': [reference_url]}
        with app.app.test_request_context('/api/aivideo/generate', method='POST', json=payload):
            app.session['mii_aivideo_auth'] = True
            with patch.object(app.threading, 'Thread', NoStartThread), patch.object(app, '_persist_task'):
                response = app.aivideo_generate()
        self.assertEqual(response.status_code, 200)
        task = app.AIVIDEO_TASKS.pop(captured['task_id'])
        diagnostic = task['diagnostic']
        self.assertEqual(diagnostic['status'], 'QUEUED')
        self.assertEqual(diagnostic['prompt_sent'], 'exact prompt')
        self.assertEqual(diagnostic['payload_summary']['quality'], 'high')
        self.assertEqual(diagnostic['references'][0]['filename'], 'reference.png')
        self.assertEqual(diagnostic['references'][0]['final_url'],
                         diagnostic['payload_summary']['reference_urls'][0])
        self.assertNotIn('Authorization', repr(diagnostic))

    def test_debug_log_reconstructs_persisted_task_after_refresh(self):
        record = {'request_id': 'MII-ABC', 'status': 'COMPLETED', 'created_at': 'now',
                  'elapsed_ms': 125, 'prompt_sent': 'safe', 'references': []}
        with patch.object(app.aivideo_archive, 'list_recent_tasks', return_value=[{'diagnostic': record}]), \
             patch.object(app.aivideo_archive, 'list_archive', return_value=[]), \
             patch.object(app._dropbox_manager, 'status', return_value={'state': 'not_connected'}):
            status = app._browser_debug_status()
        self.assertEqual(status['request_log']['total'], 1)
        self.assertEqual(status['request_log']['success'], 1)
        self.assertEqual(status['request_log']['entries'][0]['request_id'], 'MII-ABC')

    @patch.object(app, '_persist_task')
    @patch.object(app, '_fetch_generated_result', return_value=b'image')
    @patch.object(app.budgetpixel_provider, 'poll')
    @patch.object(app.budgetpixel_provider, 'submit_image')
    def test_multi_image_archive_success(self, submit, poll, fetch, persist):
        submit.return_value = {'job_id': 'private'}
        poll.return_value = {'status': 'completed', 'url': 'https://cdn/1.png',
                             'images': [{'url': 'https://cdn/1.png'}, {'url': 'https://cdn/2.png'}]}
        with patch.object(app, 'get_secret', return_value='secret'), \
             patch.object(app, '_dropbox_upload_and_link', side_effect=['https://stable/1', 'https://stable/2']):
            app.AIVIDEO_TASKS['audit-success'] = {'status': 'pending'}
            app._run_budgetpixel_task('audit-success', 'gptimage', 'STANDARD', {'prompt': 'x'}, 'image')
        task = app.AIVIDEO_TASKS.pop('audit-success')
        self.assertEqual(task['status'], 'completed')
        self.assertEqual(len(task['output']['images']), 2)

    @patch.object(app, '_persist_task')
    @patch.object(app, '_fetch_generated_result', return_value=b'image')
    @patch.object(app.budgetpixel_provider, 'poll', return_value={'status': 'completed', 'url': 'https://cdn/1.png', 'images': []})
    @patch.object(app.budgetpixel_provider, 'submit_image', return_value={'job_id': 'private'})
    def test_archive_failure_keeps_preview_and_has_distinct_code(self, submit, poll, fetch, persist):
        writer = Mock()
        writer.__enter__ = Mock(return_value=writer)
        writer.__exit__ = Mock(return_value=False)
        with patch.object(app, 'get_secret', return_value='secret'), \
             patch.object(app, '_dropbox_upload_and_link', side_effect=RuntimeError('offline')), \
             patch.object(app.os, 'makedirs'), patch('builtins.open', return_value=writer):
            app.AIVIDEO_TASKS['audit-failure'] = {'status': 'pending'}
            app._run_budgetpixel_task('audit-failure', 'gptimage', 'STANDARD', {'prompt': 'x'}, 'image')
        task = app.AIVIDEO_TASKS.pop('audit-failure')
        self.assertEqual(task['status'], 'failed')
        self.assertEqual(task['error_code'], 'RESULT_SAVE_FAILED')
        self.assertTrue(task['output']['image_url'].startswith('/static/'))


if __name__ == '__main__':
    unittest.main()
