from pathlib import Path
import unittest

import budgetpixel_provider as provider


class UniversalVideoFramesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Path('templates/ai-video.html').read_text(encoding='utf-8')

    def test_one_shared_rail_and_prompt_are_moved_between_modes(self):
        self.assertEqual(self.html.count('id="typeRail"'), 1)
        self.assertEqual(self.html.count('id="promptBtn"'), 1)
        self.assertNotIn('id="promptBtnFrames"', self.html)
        self.assertIn("railMount.appendChild(rail)", self.html)
        self.assertIn("promptMount.appendChild(promptCard)", self.html)
        self.assertLess(self.html.index('id="cardFirstFrame"'), self.html.index('id="cardLastFrame"'))
        self.assertLess(self.html.index('id="cardLastFrame"'), self.html.index('id="framesPromptMount"'))

    def test_all_frame_models_use_capabilities_not_family_names(self):
        self.assertIn('frames: !!rawCaps.supportsFirstFrame', self.html)
        self.assertIn('lastFrame: !!rawCaps.supportsEndFrame', self.html)
        for family in ('seedance25', 'seedance', 'wan30', 'kling', 'minimaxh3',
                       'pixverse', 'wan27', 'seedance15', 'kling26'):
            line = next(line for line in self.html.splitlines() if "key:'%s'" % family in line or "key: '%s'" % family in line)
            if 'caps:' not in line:  # multi-line family: inspect the following declaration block
                line += self.html[self.html.index(line):self.html.index(line) + 900]
            self.assertIn('supportsFirstFrame:true', line, family)

    def test_frame_state_is_independent_and_incompatible_payload_is_filtered(self):
        self.assertIn("var frames = { first: null, last: null }", self.html)
        self.assertIn("var selectedMedia = usingFrames ? {image:[], video:[], audio:[]} : media", self.html)
        self.assertIn("var selectedFrames = usingFrames ? frames : {first:null, last:null}", self.html)
        self.assertIn("removeFrame(which, event)", self.html)

    def test_budgetpixel_exact_frame_and_reference_mapping(self):
        body = provider.build_video_payload(
            'seedance25', 'STANDARD', {'duration': 30, 'resolution': '1080p', 'aspect_ratio': '9:16'},
            'move', first_frame='https://cdn/first.png', last_frame='https://cdn/last.png')
        self.assertEqual(body['image'], 'https://cdn/first.png')
        self.assertEqual(body['end_image'], 'https://cdn/last.png')
        # BudgetPixel's real API uses length_seconds (confirmed in their own
        # published curl example at budgetpixel.com/api), not duration_seconds.
        self.assertEqual(body['length_seconds'], 30)
        self.assertEqual(body['resolution'], '1080p')
        self.assertEqual(body['aspect_ratio'], '9:16')
        self.assertTrue(body['generate_audio'])
        refs = provider.build_video_payload(
            'wan30', 'PRIME', {'duration': 2, 'resolution': '480p'}, 'move',
            ['https://cdn/image.png'], ['https://cdn/video.mp4'], ['https://cdn/audio.mp3'])
        self.assertEqual(refs['reference_images'], ['https://cdn/image.png'])
        self.assertEqual(refs['reference_videos'], ['https://cdn/video.mp4'])
        self.assertEqual(refs['reference_audios'], ['https://cdn/audio.mp3'])
        with self.assertRaises(provider.ProviderError):
            provider.build_video_payload('wan30', 'STANDARD', {'resolution': '720p'}, 'x',
                                         ['https://cdn/ref.png'], first_frame='https://cdn/first.png')

    def test_estimate_frontend_is_disabled_and_balance_remains(self):
        self.assertNotIn("fetchWithTimeout('/api/aivideo/cost'", self.html)
        self.assertNotIn('ESTIMATE UNAVAILABLE', self.html)
        self.assertIn("fetch('/api/aivideo/credits')", self.html)


if __name__ == '__main__':
    unittest.main()
