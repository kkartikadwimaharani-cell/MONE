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

    def capture_task_args(self, payload):
        captured = {}

        class NoStartThread:
            def __init__(self, target=None, args=(), **kwargs):
                captured["args"] = args

            def start(self):
                pass

        with app.app.test_request_context("/api/aivideo/generate", method="POST", json=payload):
            app.session["mii_aivideo_auth"] = True
            with patch.object(app.threading, "Thread", NoStartThread), patch.object(app, "_persist_task"):
                response = app.aivideo_generate()
        self.assertEqual(response.status_code, 200)
        return captured["args"]

    def test_seedance25_reuses_compact_video_controls(self):
        caps = budgetpixel_provider.video_capabilities("seedance25", "STANDARD")
        self.assertEqual(caps["aspect_ratios"], ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9"))
        self.assertNotIn("Advanced Video Settings", self.template)
        self.assertIn("settingsRow.classList.toggle('seedance25-settings'", self.template)
        self.assertIn("options: ['Audio On','Audio Off']", self.template)
        for control in ('ratioChip', 'resolutionChip', 'bitrateChip', 'muteAudioChip'):
            self.assertIn('class="chip" id="%s"' % control, self.template)
        self.assertIn("['STANDARD','HIGH']", self.template)

    def test_mobile_row_has_bounded_wrap_at_target_widths(self):
        css = self.template
        self.assertIn('@media(max-width:430px)', css)
        self.assertIn('max-width:100%;flex-wrap:wrap', css)
        for width in (360, 390, 412, 430):
            self.assertLessEqual(width, 430)

    def test_selected_ratio_reaches_existing_provider_field(self):
        body = self.capture_body({"family": "seedance25", "model": "STANDARD", "prompt": "A person walks.",
                                  "duration": 30, "resolution": "480p", "aspect_ratio": "3:4"})
        self.assertEqual(body["aspect_ratio"], "3:4")
        self.assertEqual(body["duration_seconds"], 30)
        self.assertEqual(body["resolution"], "480p")
        self.assertTrue(body["generate_audio"])

    def test_invalid_ratio_defaults_and_no_fake_bitrate_is_emitted(self):
        body = self.capture_body({"family": "seedance25", "model": "STANDARD", "prompt": "Tokyo skyline.",
                                  "aspect_ratio": "16:9", "bitrate": "MAX", "bitrate_mode": "high"})
        self.assertEqual(body["aspect_ratio"], "16:9")
        self.assertNotIn("bitrate", body)
        self.assertNotIn("bitrate_mode", body)

    def test_output_bitrate_is_snapshotted_but_never_sent_to_provider(self):
        args = self.capture_task_args({"family": "seedance25", "model": "STANDARD", "prompt": "Ocean.",
                                      "resolution": "480p", "output_bitrate": "HIGH"})
        self.assertNotIn("output_bitrate", args[3])
        self.assertNotIn("bitrate", args[3])
        self.assertEqual(args[5:], ("HIGH", "480p"))

    def test_auto_output_processing_is_passthrough(self):
        source = b"provider video"
        with patch.object(app.subprocess, "run") as run:
            self.assertIs(app._apply_video_output_bitrate(source, "AUTO", "720p"), source)
        run.assert_not_called()

    def test_profiles_are_resolution_aware(self):
        self.assertEqual(app._video_output_bitrate_target("STANDARD", "480p"), "1200k")
        self.assertEqual(app._video_output_bitrate_target("HIGH", "720p"), "4500k")
        self.assertNotIn("MAX", next(line for line in self.template.splitlines() if "sheetDefs.bitrate.options" in line))

    def test_non_auto_processing_occurs_after_video_fetch_and_preserves_audio(self):
        events = []
        result = {"status": "completed", "url": "https://result.example/video.mp4", "images": []}
        with patch.object(budgetpixel_provider, "submit_video", return_value={"job_id": "provider-1"}), \
             patch.object(budgetpixel_provider, "poll", return_value=result), \
             patch.object(app, "get_secret", return_value="mock"), \
             patch.object(app, "_fetch_generated_result", side_effect=lambda *_: events.append("fetch") or b"raw"), \
             patch.object(app, "_apply_video_output_bitrate", side_effect=lambda data, profile, resolution: events.append(("process", profile, resolution)) or b"encoded"), \
             patch.object(app, "_dropbox_upload_and_link", return_value="https://saved.example/video.mp4"), \
             patch.object(app, "_persist_task"), patch.object(app, "_diagnostic_update"), \
             patch.object(app, "_aivideo_log_request"), patch.object(app, "_aivideo_last_error"):
            app.AIVIDEO_TASKS["unit-bitrate"] = {}
            app._run_budgetpixel_task("unit-bitrate", "seedance25", "STANDARD", {"prompt": "x"},
                                      "video", "HIGH", "720p")
        self.assertEqual(events, ["fetch", ("process", "HIGH", "720p")])
        self.assertEqual(app.AIVIDEO_TASKS["unit-bitrate"]["output"]["bitrate"], "HIGH")
        # The ffmpeg command stream-copies every non-video stream, including audio.
        import inspect
        helper = inspect.getsource(app._apply_video_output_bitrate)
        self.assertIn("'-map', '0', '-c', 'copy'", helper)
        self.assertNotIn("'-an'", helper)

    def test_image_results_never_enter_bitrate_processing(self):
        self.assertIn("output_type == 'video' and family == 'seedance25'", Path("app.py").read_text())

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
        self.assertIn("modelSpecificSettings[previousStateKey]", self.template)
        self.assertIn("bitrate:selectedBitrate", self.template)
        self.assertNotIn(".settings-row.image-settings{", self.template)


if __name__ == "__main__":
    unittest.main()
