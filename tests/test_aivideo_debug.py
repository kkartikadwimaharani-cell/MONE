import io
import unittest
from unittest.mock import patch

import app


class AiVideoDebugTests(unittest.TestCase):
    def setUp(self):
        with app._AIVIDEO_DEBUG_LOCK:
            app._AIVIDEO_DEBUG.update({
                'last_upload': None, 'last_uploads': [], 'last_request': None,
                'last_error': None, 'motion_control': None,
            })
        with app._AIVIDEO_REQUEST_LOG_LOCK:
            app._AIVIDEO_REQUEST_LOG.clear()

    def _upload(self, filename, final_url):
        png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
        with app.app.test_request_context(
                '/api/aivideo/upload', method='POST',
                data={'file': (io.BytesIO(png), filename)},
                content_type='multipart/form-data'):
            app.session['mii_aivideo_auth'] = True
            with patch.object(app, 'DROPBOX_ACCESS_TOKEN', 'configured'), \
                    patch.object(app, '_dropbox_upload_and_link', return_value=final_url):
                response = app.aivideo_upload()
        self.assertEqual(response.status_code, 200)

    def test_upload_history_and_forget(self):
        first = 'https://files.example/first.png'
        second = 'https://files.example/second.png'
        self._upload('first.png', first)
        self._upload('second.png', second)
        debug = app._aivideo_debug_snapshot()
        self.assertEqual(debug['last_upload']['final_url'], second)
        self.assertEqual(debug['last_upload']['media_type'], 'IMAGE')
        self.assertEqual([item['final_url'] for item in debug['last_uploads']], [first, second])

        with app.app.test_request_context('/api/aivideo/upload/forget', method='POST', json={'url': second}):
            app.session['mii_aivideo_auth'] = True
            with patch.object(app, '_dropbox_delete_by_url', return_value=(True, 'deleted')):
                response = app.aivideo_upload_forget()
        self.assertEqual(response.status_code, 200)
        debug = app._aivideo_debug_snapshot()
        self.assertIsNone(debug['last_upload'])
        self.assertEqual([item['final_url'] for item in debug['last_uploads']], [first])

    def test_generate_records_incoming_and_exact_final_references(self):
        url = 'https://files.example/reference.png'
        self._upload('reference.png', url)
        captured = {}

        class NoStartThread:
            def __init__(self, target=None, args=(), **kwargs):
                captured['task_id'], captured['body'] = args[0], args[3]
            def start(self):
                pass

        payload = {'family': 'gptimage', 'model': 'HIGH', 'prompt': 'diagnostic prompt',
                   'quality': 'HIGH', 'resolution': '4K', 'num_images': 2,
                   'output_format': 'png', 'aspect_ratio': '16:9', 'image_urls': [url]}
        with app.app.test_request_context('/api/aivideo/generate', method='POST', json=payload):
            app.session['mii_aivideo_auth'] = True
            with patch.object(app.threading, 'Thread', NoStartThread), patch.object(app, '_persist_task'):
                response = app.aivideo_generate()
        self.assertEqual(response.status_code, 200)
        diagnostic = app.AIVIDEO_TASKS.pop(captured['task_id'])['diagnostic']
        self.assertEqual(diagnostic['incoming_payload']['image_urls'], [url])
        self.assertEqual(diagnostic['final_payload']['reference_images'], [url])
        self.assertEqual(captured['body']['reference_images'], [url])

    def test_budgetpixel_lifecycle_updates_one_record_and_safe_error(self):
        task_id = 'mock-lifecycle'
        app.AIVIDEO_TASKS[task_id] = {'status': 'pending', 'created': 1,
            'diagnostic': {'request_id': 'MII-MOCK', 'created_ts': 1, 'status': 'QUEUED'}}
        with patch.object(app, 'get_secret', return_value='private-key'), \
                patch.object(app.budgetpixel_provider, 'submit_image', return_value={'job_id': 'private-job'}), \
                patch.object(app.budgetpixel_provider, 'poll', return_value={'status': 'completed', 'url': 'https://result', 'images': []}), \
                patch.object(app, '_fetch_generated_result', return_value=b'image'), \
                patch.object(app, '_dropbox_upload_and_link', return_value='https://archive/result.png'), \
                patch.object(app, '_persist_task'):
            app._run_budgetpixel_task(task_id, 'gptimage', 'HIGH', {'prompt': 'safe'}, 'image')
        task = app.AIVIDEO_TASKS.pop(task_id)
        self.assertEqual(task['diagnostic']['status'], 'COMPLETED')
        self.assertEqual(len(app._AIVIDEO_REQUEST_LOG), 1)
        self.assertNotIn('private-job', repr(app._AIVIDEO_REQUEST_LOG))

        app._aivideo_last_error('provider', 'Authorization: Bearer top-secret api_key=hidden')
        error = app._aivideo_debug_snapshot()['last_error']
        self.assertNotIn('top-secret', repr(error))
        self.assertNotIn('=hidden', repr(error))

    def test_clear_only_resets_diagnostics(self):
        app._aivideo_debug_set('last_request', body={'prompt': 'x'})
        app._aivideo_debug_append_upload({'url': 'https://files.example/x'})
        app._aivideo_log_request('mock', 'generation', status_code=200)
        archive_marker = {'history': 'must remain'}
        with app.app.test_request_context('/ai-video/debug/clear'):
            app.session['mii_aivideo_auth'] = True
            response = app.ai_video_debug_clear()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(archive_marker, {'history': 'must remain'})
        self.assertIsNone(app._aivideo_debug_snapshot()['last_request'])
        self.assertEqual(app._aivideo_debug_snapshot()['last_uploads'], [])
        self.assertEqual(app._AIVIDEO_REQUEST_LOG, [])


if __name__ == '__main__':
    unittest.main()
