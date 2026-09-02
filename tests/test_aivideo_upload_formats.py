import io
import unittest
from unittest.mock import patch

import app


PNG = (b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR'
       + b'\x00\x00\x00\x01\x00\x00\x00\x01' + b'\x08\x06\x00\x00\x00')
JPEG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00' + b'valid-jpeg-payload' + b'\xff\xd9'
WEBP = b'RIFF\x16\x00\x00\x00WEBPVP8 ' + b'\x0a\x00\x00\x00' + b'webp-bytes'


class AiVideoUploadFormatTests(unittest.TestCase):
    def upload(self, filename, content, browser_mime=None, media_type='image'):
        uploaded = {}

        def relay(data, storage_filename):
            uploaded.update(data=data, filename=storage_filename)
            return 'https://files.example/' + storage_filename

        file_value = ((io.BytesIO(content), filename, browser_mime)
                      if browser_mime is not None else (io.BytesIO(content), filename))
        with app.app.test_request_context(
                '/api/aivideo/upload', method='POST',
                data={'file': file_value, 'media_type': media_type},
                content_type='multipart/form-data'):
            app.session['mii_aivideo_auth'] = True
            with patch.object(app, 'DROPBOX_ACCESS_TOKEN', 'configured'), \
                    patch.object(app, '_dropbox_upload_and_link', side_effect=relay):
                response = app.aivideo_upload()
        response = app.app.make_response(response)
        return response, response.get_json(), uploaded

    def test_supported_images_are_accepted_without_reencoding(self):
        cases = [
            ('reference.jpg', JPEG, 'image/jpeg'),
            ('reference.jpeg', JPEG, 'image/pjpeg'),
            ('reference.png', PNG, 'image/png'),
            ('reference.webp', WEBP, 'image/webp'),
        ]
        for filename, content, browser_mime in cases:
            with self.subTest(filename=filename):
                response, body, uploaded = self.upload(filename, content, browser_mime)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(body['ok'])
                self.assertEqual(uploaded['data'], content)
                self.assertEqual(uploaded['filename'], filename)

    def test_mobile_missing_or_ambiguous_mime_uses_detected_content(self):
        for browser_mime in (None, 'application/octet-stream'):
            with self.subTest(browser_mime=browser_mime):
                response, body, uploaded = self.upload('mobile.jpeg', JPEG, browser_mime)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(body['ok'])
                self.assertEqual(uploaded['data'], JPEG)

    def test_jpeg_with_png_name_is_detected_and_safely_renamed(self):
        response, body, uploaded = self.upload('camera.png', JPEG, 'image/png')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body['ok'])
        self.assertEqual(uploaded['data'], JPEG)
        self.assertEqual(uploaded['filename'], 'camera.jpg')

    def test_fake_png_and_unsupported_image_are_rejected_publicly(self):
        for filename, content, browser_mime in (
                ('fake.png', b'not an image', 'image/png'),
                ('animation.gif', b'GIF89a-not-enabled', 'image/gif')):
            with self.subTest(filename=filename):
                response, body, uploaded = self.upload(filename, content, browser_mime)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(body['error'], app._IMAGE_FORMAT_ERROR)
                self.assertEqual(uploaded, {})

    def test_media_capabilities_remain_separate(self):
        response, body, uploaded = self.upload('audio.mp3', b'ID3audio', 'audio/mpeg', 'image')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body['error'], app._IMAGE_FORMAT_ERROR)
        self.assertEqual(uploaded, {})


if __name__ == '__main__':
    unittest.main()
