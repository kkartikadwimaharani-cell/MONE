from pathlib import Path
import re
import unittest


class AiVideoModelStateTests(unittest.TestCase):
    """Cheap source-contract tests for the dependency-free single-page UI."""

    @classmethod
    def setUpClass(cls):
        cls.source = Path("templates/ai-video.html").read_text(encoding="utf-8")

    def function_body(self, name, _next_name=None):
        match = re.search(rf"function {name}\([^)]*\) \{{", self.source)
        self.assertIsNotNone(match, name)
        start = match.end()
        depth = 1
        for index in range(start, len(self.source)):
            if self.source[index] == "{":
                depth += 1
            elif self.source[index] == "}":
                depth -= 1
                if depth == 0:
                    return self.source[start:index]
        self.fail(f"unterminated function: {name}")

    def test_markup_has_no_competing_seedance20_default(self):
        self.assertIn('id="modelSelectTxt">Loading model…</span>', self.source)
        self.assertIn('id="collapsedModelTxt">Loading model…</span>', self.source)
        self.assertIn('id="modelSelectTier"></span>', self.source)

    def test_clean_boot_uses_primary_video_family_through_central_sync(self):
        self.assertRegex(self.source, r"video:\s*\[\s*\{\s*key: 'seedance25'")
        self.assertIn("var DEFAULT_VIDEO_FAMILY_KEY = 'seedance25';", self.source)
        self.assertIn("var bootModelState = resolveCanonicalModelState(activeMode);", self.source)
        self.assertIn("applySelectedFamily(bootModelState.family, bootModelState.qualityIdx,", self.source)
        self.assertNotIn("var restoredModelState", self.source)

    def test_central_sync_updates_every_model_surface_and_seedance25_defaults(self):
        body = self.function_body("applySelectedFamily", "pickFamily")
        for statement in (
            "selectedFamily = family",
            "selectedQualityIdx = qualityIdx",
            "selectedModel =",
            "selectedModelName = family.name",
            "selectedModelTier =",
            "'modelSelectTxt'",
            "updateCollapsedBar(family.name)",
            "renderQualityChip()",
            "applyModelCapabilities()",
            "updateCreditEstimate()",
            "updateGenerateButtonState()",
            "persistCanonicalModelState()",
        ):
            self.assertIn(statement, body)
        self.assertIn("family.key === 'seedance25' && resetFamilyDefaults", body)
        self.assertIn("selectedRatio = '16:9'", body)
        self.assertIn("selectedResolution = '720p'", body)
        self.assertIn("selectedDuration = 5", body)
        self.assertIn("muteAudioEnabled = false", body)

    def test_manual_family_and_quality_selection_share_sync_path(self):
        pick_family = self.function_body("pickFamily", "loadCanonicalModelState")
        self.assertIn("applySelectedFamily(family, qualityIdx", pick_family)
        pick_quality = self.function_body("pickQuality", "renderMuteAudioChip")
        self.assertIn("applySelectedFamily(selectedFamily, idx", pick_quality)

    def test_persisted_variant_is_strictly_family_scoped(self):
        resolver = self.function_body("resolveCanonicalModelState", "persistCanonicalModelState")
        self.assertIn("item.key === saved.family", resolver)
        self.assertIn("item.id === saved.variant", resolver)
        self.assertIn("family: fallbackFamily, qualityIdx: 0, saved: null", resolver)
        persisted = self.function_body("persistCanonicalModelState", "resolveEffectiveCapabilities")
        for field in ("family:selectedFamily.key", "variant:selectedModel", "ratio:selectedRatio",
                      "resolution:selectedResolution", "duration:selectedDuration", "muteAudio:muteAudioEnabled"):
            self.assertIn(field, persisted)

    def test_mode_switch_restores_its_own_canonical_state(self):
        body = self.function_body("setView", "updateModeUI")
        self.assertIn("resolveCanonicalModelState(activeMode)", body)
        self.assertIn("applySelectedFamily(canonical.family, canonical.qualityIdx", body)

    def test_picker_selection_uses_the_authoritative_family(self):
        self.assertIn("family.key === selectedFamily.key ? ' selected'", self.source)
        self.assertIn("document.getElementById('modelSelectTxt').textContent = family.name", self.source)


if __name__ == "__main__":
    unittest.main()
