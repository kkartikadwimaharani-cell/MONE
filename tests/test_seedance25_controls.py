from pathlib import Path
import unittest
from unittest.mock import patch

import app
import budgetpixel_provider


class Seedance25ControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = Path("templates/ai-video.html").read_text(encoding="utf-8")

    def capture_body(self, payload):
        captured = {}

        class NoStartThread:
            def __init__(self, target=None, args=(), **kwargs):
                captured["body"] = args[3]

            def start(self):
                pass

        with app.app.test_request_context("/api/aivideo/generate", method="POST", json=payload):
            app.session["mii_aivideo_auth"] = True
            with patch.object(app.threading, "Thread", NoStartThread), patch.object(app, "_persist_task"):
                response = app.aivideo_generate()
        self.assertEqual(response.status_code, 200)
        return captured["body"]

    def test_seedance25_reuses_compact_video_controls(self):
        caps = budgetpixel_provider.video_capabilities("seedance25", "STANDARD")
        self.assertEqual(caps["aspect_ratios"], ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9"))
        self.assertNotIn("Advanced Video Settings", self.template)
        self.assertIn("settingsRow.classList.toggle('seedance25-settings'", self.template)
        self.assertIn("options: ['Audio On','Audio Off']", self.template)

    def test_selected_ratio_reaches_existing_provider_field(self):
        body = self.capture_body({"family": "seedance25", "model": "STANDARD", "prompt": "A person walks.",
                                  "duration": 30, "resolution": "480p", "aspect_ratio": "3:4"})
        self.assertEqual(body["aspect_ratio"], "3:4")
        self.assertEqual(body["length_seconds"], 30)
        self.assertEqual(body["resolution"], "480p")
        self.assertTrue(body["generate_audio"])

    def test_invalid_ratio_defaults_and_no_fake_bitrate_is_emitted(self):
        body = self.capture_body({"family": "seedance25", "model": "STANDARD", "prompt": "Tokyo skyline.",
                                  "aspect_ratio": "2:1", "bitrate": "MAX", "bitrate_mode": "high"})
        self.assertEqual(body["aspect_ratio"], "16:9")
        self.assertNotIn("bitrate", body)
        self.assertNotIn("bitrate_mode", body)

    def test_audio_off_uses_verified_generate_audio_field(self):
        body = self.capture_body({"family": "seedance25", "model": "STANDARD", "prompt": "A person smiles.",
                                  "mute_audio": True})
        self.assertFalse(body["generate_audio"])

    def test_model_switching_is_capability_driven_and_image_caps_unchanged(self):
        seedance25_line = next(line for line in self.template.splitlines() if "durationMax:30" in line and "seedance25" not in line)
        self.assertIn("aspectRatios", seedance25_line)
        wan_line = next(line for line in self.template.splitlines() if "key:'wan30'" in line)
        self.assertNotIn("aspectRatios", wan_line)
        self.assertEqual(budgetpixel_provider.image_capabilities("gptimage", "HIGH")["image_count"], (1, 4))


if __name__ == "__main__":
    unittest.main()
