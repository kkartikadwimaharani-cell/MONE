import unittest

from app import _build_seedance20_payload


URL = 'https://cdn.example.com/'


class Seedance20PayloadTests(unittest.TestCase):
    def build(self, variant='MINI', images=None, videos=None, audios=None,
              first='', last='', **settings):
        payload = {'duration': settings.get('duration', 10),
                   'resolution': settings.get('resolution', '720p'),
                   'aspect_ratio': settings.get('aspect_ratio', '16:9')}
        return _build_seedance20_payload(payload, 'prompt', variant, images or [], videos or [],
                                          audios or [], first, last)

    def test_t2v_uses_duration_seconds_for_every_variant(self):
        for variant in ('MINI', 'FAST', 'PRO'):
            body = self.build(variant)
            self.assertEqual(body['duration_seconds'], 10)
            self.assertNotIn('duration', body)
            self.assertTrue(body['generate_audio'])

    def test_reference_images_and_frames_use_exact_fields(self):
        images = [URL + 'ref-%d.jpg' % index for index in range(9)]
        self.assertEqual(self.build(images=images)['reference_images'], images)
        first, last = URL + 'first.jpg', URL + 'last.jpg'
        body = self.build(first=first, last=last)
        self.assertEqual(body['image'], first)
        self.assertEqual(body['end_image'], last)
        self.assertNotIn('reference_images', body)

    def test_video_edit_and_audio_use_reference_arrays(self):
        video, audio = URL + 'edit.mp4', URL + 'guide.mp3'
        images = [URL + 'ref-%d.jpg' % index for index in range(6)]
        body = self.build(images=images, videos=[video], audios=[audio])
        self.assertEqual(body['reference_videos'], [video])
        self.assertEqual(body['reference_audios'], [audio])

    def test_variant_resolution_contract(self):
        for variant in ('MINI', 'FAST'):
            self.assertEqual(self.build(variant, resolution='4K')['resolution'], '720p')
            self.assertEqual(self.build(variant, resolution='480p')['resolution'], '480p')
        for resolution in ('480p', '720p', '1080p', '4K'):
            self.assertEqual(self.build('PRO', resolution=resolution)['resolution'], resolution)

    def test_invalid_combinations_and_limits_are_rejected(self):
        invalid = [
            dict(images=[URL + 'x.jpg'], first=URL + 'first.jpg'),
            dict(videos=[URL + 'x.mp4'], first=URL + 'first.jpg'),
            dict(last=URL + 'last.jpg'),
            dict(audios=[URL + 'x.mp3']),
            dict(images=[URL + '%d.jpg' % i for i in range(10)]),
            dict(videos=[URL + 'x.mp4'], images=[URL + '%d.jpg' % i for i in range(7)]),
            dict(videos=[URL + 'a.mp4', URL + 'b.mp4']),
            dict(audios=[URL + 'a.mp3', URL + 'b.mp3'], images=[URL + 'x.jpg']),
        ]
        for inputs in invalid:
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                self.build(**inputs)

    def test_private_or_empty_fields_are_never_forwarded(self):
        with self.assertRaises(ValueError):
            self.build(images=['http://localhost:5000/static/ref.jpg'])
        body = self.build()
        self.assertEqual(set(body), {'prompt', 'duration_seconds', 'resolution', 'aspect_ratio', 'generate_audio'})


if __name__ == '__main__':
    unittest.main()
