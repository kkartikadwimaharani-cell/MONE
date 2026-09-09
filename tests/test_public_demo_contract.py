from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO = (ROOT / "templates" / "ai-video.html").read_text()
HOME = (ROOT / "templates" / "index.html").read_text()


def test_public_demo_copy_and_home_card_are_compact_and_unique():
    assert "PUBLIC DEMO // SAFE MODE" in DEMO
    assert "GENERASI, UPLOAD, POLLING, DAN KREDIT DINONAKTIFKAN." in DEMO
    assert HOME.count("MII AI VIDEO · PUBLIC DEMO") == 1
    assert "UI PREVIEW // TANPA GENERASI · TANPA KREDIT" in HOME
    assert 'href="/mii-ai-video"' in HOME


def test_primary_demo_controls_are_native_buttons():
    for control_id in (
        "ratioChip", "resolutionChip", "imageFormatChip", "bitrateChip",
        "motionChip", "audioFormatChip", "sampleRateChip", "audioModeChip",
        "audioLyricsChip", "vocalGenderChip", "muteAudioChip",
        "imageQualityControl", "imageCountControl", "imageAdvancedControl",
    ):
        assert f'<button type="button" class="chip" id="{control_id}"' in DEMO
    assert DEMO.count('<button type="button" class="mode-btn') == 3
    assert "b.setAttribute('aria-selected', 'false')" in DEMO


def test_demo_is_fail_closed_before_other_fetch_wrappers_load():
    demo_guard = DEMO.index("PUBLIC_DEMO_NETWORK_DISABLED")
    csrf_wrapper = DEMO.index("CSRF: auto-attach token")
    assert demo_guard < csrf_wrapper
    assert "if (DEMO_MODE) { showDemoNotice('generate'); return; }" in DEMO
    assert "if (DEMO_MODE) { showDemoNotice('reference'); return; }" in DEMO
    assert "if (DEMO_MODE) return; fetch('/api/aivideo/credits')" in DEMO


def test_variant_switch_resets_then_clamps_capability_state():
    assert "previousVariantId !== selectedModel" in DEMO
    assert "selectedDuration = rawCaps.defaultDuration" in DEMO
    assert "selectedResolution = rawCaps.defaultResolution || opts[0]" in DEMO
    assert "media.image.slice(0, activeLimit('maxReferenceImages', 'image'))" in DEMO
