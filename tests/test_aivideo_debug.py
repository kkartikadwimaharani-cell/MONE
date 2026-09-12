import io
import sqlite3
import unittest
from unittest.mock import patch

import app
import aivideo_archive


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
        png = (b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR'
               + b'\x00\x00\x00\x01\x00\x00\x00\x01' + b'\x08\x06\x00\x00\x00')
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
        with app.app.test_request_context('/ai-video/debug/clear', method='POST'):
            app.session['mii_aivideo_auth'] = True
            response = app.ai_video_debug_clear()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(archive_marker, {'history': 'must remain'})
        self.assertIsNone(app._aivideo_debug_snapshot()['last_request'])
        self.assertEqual(app._aivideo_debug_snapshot()['last_uploads'], [])
        self.assertEqual(app._AIVIDEO_REQUEST_LOG, [])


    def test_security_history_is_independent_and_password_protected(self):
        event = {'created_ts': 1700000000, 'kind': 'DENIED WRITE REQUEST',
                 'route': '/api/aivideo/generate', 'ip_address': '<script>alert(1)</script>',
                 'socket_ip': '127.0.0.1', 'ip_source': 'UNVERIFIED PROXY HEADER',
                 'device': 'Android Chrome', 'http_status': 401}
        with app.app.test_client() as client, \
                patch.object(app, 'get_site_status', return_value={'maintenance': False}), \
                patch.object(app.aivideo_archive, 'list_security_events',
                             return_value={'count': 1, 'retention_days': 30, 'events': [event]}) as read, \
                patch.object(app._dropbox_manager, 'status') as storage:
            locked = client.get('/ai-video/security-history')
            self.assertEqual(locked.status_code, 200)
            self.assertIn(b'PRIVATE WORKSPACE', locked.data)
            read.assert_not_called()
            with client.session_transaction() as sess:
                sess['mii_aivideo_auth'] = True
            page = client.get('/ai-video/security-history')
            self.assertEqual(page.status_code, 200)
            self.assertIn(b'SECURITY HISTORY', page.data)
            self.assertIn(b'DENIED WRITE REQUEST', page.data)
            self.assertNotIn(b'<script>alert(1)</script>', page.data)
            self.assertIn(b'&lt;script&gt;', page.data)
            self.assertIn(b'no-store', page.headers['Cache-Control'])
            read.assert_called_once_with(limit=100)
            storage.assert_not_called()

    def test_security_history_failure_is_rendered_without_debug_dependency(self):
        with app.app.test_client() as client, \
                patch.object(app, 'get_site_status', return_value={'maintenance': False}), \
                patch.object(app.aivideo_archive, 'list_security_events',
                             side_effect=RuntimeError('temporary database failure')):
            with client.session_transaction() as sess:
                sess['mii_aivideo_auth'] = True
            page = client.get('/ai-video/security-history')
            self.assertEqual(page.status_code, 200)
            self.assertIn(b'HISTORY TEMPORARILY UNAVAILABLE', page.data)
            self.assertNotIn(b'AUDIT READY', page.data)

    def test_debug_payload_does_not_load_security_history(self):
        with app.app.test_request_context('/api/aivideo/debug-data'), \
                patch.object(app.aivideo_archive, 'list_security_events') as read, \
                patch.object(app._dropbox_manager, 'status', return_value={'state': 'NOT CONFIGURED'}), \
                patch.object(app.budgetpixel_registry, 'get_registry',
                             return_value={'models': [], 'synced_at': None, 'sync_error': None}):
            result = app._aivideo_diagnostics()
            self.assertNotIn('security_history', result)
            read.assert_not_called()

    def test_security_history_only_records_threshold_and_denied_writes(self):
        with app._AIVIDEO_UNLOCK_LOCK:
            app._AIVIDEO_UNLOCK_ATTEMPTS.clear()
            app._AIVIDEO_GLOBAL_FAILS.clear()
            app._AIVIDEO_GLOBAL_LOCK_UNTIL = 0
        with app.app.test_client() as client, \
                patch.object(app, 'get_site_status', return_value={'maintenance': False}), \
                patch.object(app, '_mii_aivideo_password', return_value='correct-password'), \
                patch.object(app.aivideo_archive, 'record_unlock_attempt', return_value=(0, 0)), \
                patch.object(app.aivideo_archive, 'record_security_event') as recorder:
            for _ in range(2):
                self.assertEqual(client.post('/ai-video/unlock', json={'password': 'wrong-password'}, headers={'CF-Connecting-IP': '203.0.113.8', 'User-Agent': 'Android Chrome'}).status_code, 401)
            self.assertEqual(recorder.call_count, 0)
            self.assertEqual(client.post('/ai-video/unlock', json={'password': 'wrong-password'},
                                         headers={'CF-Connecting-IP': '203.0.113.8',
                                                  'User-Agent': 'Android Chrome'}).status_code, 423)
            self.assertEqual(recorder.call_count, 1)
            self.assertEqual(recorder.call_args.args[0], 'PASSWORD LOCKOUT THRESHOLD')
            self.assertEqual(recorder.call_args.args[3], '127.0.0.1')
            self.assertNotIn('wrong-password', repr(recorder.call_args))
            self.assertEqual(client.post('/api/aivideo/generate', json={'prompt': 'private prompt'},
                                         headers={'User-Agent': 'Android Chrome'}).status_code, 401)
            self.assertEqual(recorder.call_count, 2)
            self.assertNotIn('private prompt', repr(recorder.call_args))
            self.assertEqual(client.get('/api/aivideo/debug-data',
                                        headers={'Authorization': 'Bearer example'}).status_code, 401)
        with app._AIVIDEO_UNLOCK_LOCK:
            app._AIVIDEO_UNLOCK_ATTEMPTS.clear()
            app._AIVIDEO_GLOBAL_FAILS.clear()
            app._AIVIDEO_GLOBAL_LOCK_UNTIL = 0

    def test_security_history_bounded_and_deduplicated(self):
        conn = sqlite3.connect(':memory:', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            with patch.object(aivideo_archive, '_get_conn', return_value=conn):
                self.assertTrue(aivideo_archive.record_security_event(
                    'PASSWORD LOCKOUT THRESHOLD', '/ai-video/unlock', '203.0.113.8',
                    '127.0.0.1', 'UNVERIFIED PROXY HEADER', 'Android Chrome', 423))
                self.assertFalse(aivideo_archive.record_security_event(
                    'PASSWORD LOCKOUT THRESHOLD', '/ai-video/unlock', '203.0.113.8',
                    '127.0.0.1', 'UNVERIFIED PROXY HEADER', 'Android Chrome', 423))
                events = aivideo_archive.list_security_events()['events']
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]['ip_source'], 'UNVERIFIED PROXY HEADER')
                self.assertEqual(events[0]['device'], 'Android Chrome')
        finally:
            conn.close()

    def test_debug_clear_requires_post_and_csrf(self):
        with app.app.test_client() as client, \
                patch.object(app, 'get_site_status', return_value={'maintenance': False}):
            with client.session_transaction() as sess:
                sess['mii_aivideo_auth'] = True
                sess['mii_csrf'] = 'csrf-value'
            self.assertEqual(client.get('/ai-video/debug/clear').status_code, 405)
            self.assertEqual(client.post('/ai-video/debug/clear').status_code, 403)
            self.assertEqual(client.post('/ai-video/debug/clear',
                                         headers={'X-CSRF-Token': 'csrf-value'}).status_code, 302)


    def test_dropbox_debug_status_reflects_real_test_and_redacts_metadata(self):
        now = app.time.time()
        state = {
            'state': 'connected', 'source': 'oauth',
            'account_name': 'Studio Account', 'account_id_masked': 'dbid:***',
            'auto_refresh': True, 'last_refresh_at': now - 30,
            'last_test_at': None, 'last_test_ok': None,
        }
        with app.app.test_request_context('/api/aivideo/debug-data'), \
                patch.object(app._dropbox_manager, 'status', return_value=state), \
                patch.object(app.budgetpixel_registry, 'get_registry',
                             return_value={'models': [], 'synced_at': None, 'sync_error': None}):
            app._aivideo_debug_set('dropbox', mode='oauth_connected',
                                  detail='Bearer should-not-leak', ok=None)
            unchecked = app._aivideo_diagnostics()
            self.assertEqual(unchecked['storage']['status'], 'NOT CHECKED')
            self.assertNotIn('should-not-leak', repr(unchecked))
            self.assertEqual(unchecked['dropbox']['account_id_masked'], 'dbid:***')
            state.update(last_test_at=now - 20, last_test_ok=True)
            self.assertEqual(app._aivideo_diagnostics()['storage']['status'], 'READY')
            state['last_test_at'] = now - 700
            self.assertEqual(app._aivideo_diagnostics()['storage']['status'], 'NOT CHECKED')
            state['last_test_ok'] = False
            self.assertEqual(app._aivideo_diagnostics()['storage']['status'], 'ERROR')
            state.update(state='not_connected', last_test_ok=False)
            self.assertEqual(app._aivideo_diagnostics()['storage']['status'], 'NOT CONFIGURED')

    def test_dropbox_debug_action_requires_browser_session_and_csrf(self):
        with app.app.test_client() as client, \
                patch.object(app, 'get_site_status', return_value={'maintenance': False}), \
                patch.object(app._dropbox_manager, 'test_connection',
                             return_value={'account_name': 'Studio Account',
                                           'account_id_masked': 'dbid:***'}) as test_connection, \
                patch.object(app._dropbox_manager, 'status',
                             return_value={'state': 'connected', 'source': 'oauth',
                                           'last_test_at': None, 'last_test_ok': None}):
            self.assertEqual(client.get('/api/aivideo/dropbox/status').status_code, 401)
            self.assertEqual(client.post('/api/aivideo/dropbox/test').status_code, 401)
            test_connection.assert_not_called()
            with client.session_transaction() as sess:
                sess['mii_aivideo_auth'] = True
                sess['mii_csrf'] = 'test-csrf'
            page = client.get('/ai-video/debug')
            self.assertIn(b'MANAGE DROPBOX', page.data)
            self.assertIn(b'TEST CONNECTION', page.data)
            self.assertEqual(client.post('/api/aivideo/dropbox/test').status_code, 403)
            test_connection.assert_not_called()
            passed = client.post('/api/aivideo/dropbox/test',
                                 headers={'X-CSRF-Token': 'test-csrf'})
            self.assertEqual(passed.status_code, 200)
            test_connection.assert_called_once_with()

if __name__ == '__main__':
    unittest.main()
