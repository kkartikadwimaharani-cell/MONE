import unittest

from app import _build_seedance20_payload


URL = 'https://cdn.example.com/'


class Seedance20PayloadTests(unittest.TestCase):
    """Segmind's real Seedance 2.0 contract (segmind.com/models/seedance-2.0/api):
    field names are duration/first_frame_url/last_frame_url/reference_images/
    reference_videos/reference_audios — NOT the BudgetPixel naming used by
    seedance25/wan30. See app.py's _build_seedance20_payload docstring."""

    def build(self, variant='MINI', images=None, videos=None, audios=None,
              first='', last='', **settings):
        payload = {'duration': settings.get('duration', 10),
                   'resolution': settings.get('resolution', '720p'),
                   'aspect_ratio': settings.get('aspect_ratio', '16:9')}
        return _build_seedance20_payload(payload, 'prompt', variant, images or [], videos or [],
                                          audios or [], first, last)

    def test_t2v_uses_duration_for_every_variant(self):
        for variant in ('MINI', 'FAST', 'PRO'):
            body = self.build(variant)
            self.assertEqual(body['duration'], 10)
            self.assertTrue(body['generate_audio'])

    def test_reference_images_and_frames_use_exact_fields(self):
        images = [URL + 'ref-%d.jpg' % index for index in range(9)]
        self.assertEqual(self.build(images=images)['reference_images'], images)
        first, last = URL + 'first.jpg', URL + 'last.jpg'
        body = self.build(first=first, last=last)
        self.assertEqual(body['first_frame_url'], first)
        self.assertEqual(body['last_frame_url'], last)
        self.assertNotIn('reference_images', body)

    def test_video_and_audio_use_reference_arrays(self):
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

    def test_invalid_combinations_are_rejected(self):
        # Confirmed in Segmind's own Seedance 2.0 error guide: first/last
        # frame mode and reference_images mode are mutually exclusive, and
        # last_frame_url requires first_frame_url.
        invalid = [
            dict(images=[URL + 'x.jpg'], first=URL + 'first.jpg'),
            dict(last=URL + 'last.jpg'),
            dict(audios=[URL + 'x.mp3']),
        ]
        for inputs in invalid:
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                self.build(**inputs)

    def test_video_reference_can_combine_with_first_frame(self):
        # Unlike reference_images, reference_videos is not documented as
        # mutually exclusive with first_frame_url.
        body = self.build(videos=[URL + 'x.mp4'], first=URL + 'first.jpg')
        self.assertEqual(body['reference_videos'], [URL + 'x.mp4'])
        self.assertEqual(body['first_frame_url'], URL + 'first.jpg')

    def test_media_lists_are_capped_at_segmind_limits(self):
        # Segmind's docs cap these at 9 images / 3 videos / 3 audios per
        # request regardless of what the client sends.
        images = [URL + '%d.jpg' % i for i in range(12)]
        videos = [URL + 'a.mp4', URL + 'b.mp4', URL + 'c.mp4', URL + 'd.mp4']
        audios = [URL + 'a.mp3', URL + 'b.mp3', URL + 'c.mp3', URL + 'd.mp3']
        body = self.build(images=images, videos=videos, audios=audios)
        self.assertEqual(len(body['reference_images']), 9)
        self.assertEqual(len(body['reference_videos']), 3)
        self.assertEqual(len(body['reference_audios']), 3)

    def test_only_documented_fields_are_forwarded(self):
        body = self.build()
        self.assertEqual(set(body), {'prompt', 'duration', 'resolution', 'aspect_ratio',
                                      'generate_audio', 'return_last_frame', 'skip_moderation',
                                      'bitrate_mode'})


if __name__ == '__main__':
    unittest.main()
