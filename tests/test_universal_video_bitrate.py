from pathlib import Path
import unittest
from unittest.mock import patch

import app


class UniversalVideoBitrateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = Path("templates/ai-video.html").read_text(encoding="utf-8")

    def test_generator_has_no_credit_or_estimate_ui(self):
        self.assertNotIn('class="chip credit-chip"', self.template)
        self.assertNotIn('id="creditBalanceTxt"', self.template)
        self.assertNotIn('id="creditCostTxt"', self.template)

    def test_bitrate_is_capability_driven_for_every_video_family(self):
        self.assertIn("activeMode === 'video' && !!selectedFamily && modelProducesVideo", self.template)
        self.assertIn("sheetDefs.bitrate.options = ['STANDARD','HIGH']", self.template)
        self.assertIn("var selectedBitrate = 'HIGH'", self.template)
        self.assertNotIn("bitrateChip.classList.toggle('locked'", self.template)

    def test_universal_preference_is_the_only_client_bitrate_field(self):
        self.assertIn("body.output_bitrate = selectedBitrate", self.template)
        self.assertNotIn("body.bitrate_mode = selectedBitrate", self.template)

    def test_seedance_fast_stays_on_verified_provider_boundary(self):
        self.assertEqual(app.SEGMIND_MODEL_MAP["FAST"], "seedance-2.0-fast")
        source = Path("app.py").read_text(encoding="utf-8")
        self.assertIn("family == 'seedance' and model_key == 'FAST'", source)
        self.assertIn("if model_key == 'PRO':", source)

    def test_low_bitrate_provider_result_is_not_reencoded(self):
        probe = type("Probe", (), {"stdout": b"1000000"})()
        source = b"provider video"
        with patch.object(app.subprocess, "run", return_value=probe) as run:
            self.assertIs(app._apply_video_output_bitrate(source, "STANDARD", "720p"), source)
        self.assertEqual(run.call_count, 1)

    def test_profiles_have_only_canonical_values_and_high_is_higher(self):
        for profiles in app.VIDEO_OUTPUT_BITRATE_PROFILES.values():
            self.assertEqual(set(profiles), {"STANDARD", "HIGH"})
            self.assertGreater(int(profiles["HIGH"][:-1]), int(profiles["STANDARD"][:-1]))


if __name__ == "__main__":
    unittest.main()
