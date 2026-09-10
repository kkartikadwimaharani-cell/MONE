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


def test_wide_layout_keeps_mobile_style_bottom_composer():
    desktop_css = DEMO.split("@media (min-width:1100px){", 1)[1].split("@media (min-width:1440px){", 1)[0]
    assert "#pageAiVideo.active{\n    display:flex;flex-direction:column" in desktop_css
    assert "grid-template-columns" not in desktop_css
    assert "grid-column:2" not in desktop_css
    assert "#pageAiVideo>.panel-wrap" in desktop_css
    assert "width:min(760px,100%)" in desktop_css


def test_gpt_image_25_uses_shared_backend_catalog_not_a_ui_placeholder():
    assert "var GPT_IMAGE_25_FAMILY" not in DEMO
    assert "var UI_ONLY_FAMILY_KEYS = [];" in DEMO
    assert "var UI_ONLY_MODEL_IDS = [];" in DEMO
    assert "if (!isBackendConnected()) { showToast('UI PREVIEW · UPLOAD BELUM DIAKTIFKAN'); return; }" in DEMO

    backend_sources = "\n".join(
        (ROOT / name).read_text()
        for name in (
            "app.py", "budgetpixel_media_catalog.py", "budgetpixel_provider.py",
            "budgetpixel_registry.py", "mii_mcp.py",
        )
    )
    assert "gpt-image-2.5-flare" in backend_sources
    assert "gpt-image-2.5-sunburst" in backend_sources


def test_image_detail_chip_names_the_real_capability():
    assert "rawCaps.supportsMegapixel ? 'MEGAPIXEL' : (rawCaps.supportsSize ? 'SIZE' : 'RESOLUTION')" in DEMO


def test_coarse_pointer_desktop_site_keeps_mobile_density_and_pet_alignment():
    coarse_css = DEMO.split("@media (pointer:coarse) and (min-width:768px){", 1)[1].split("</style>", 1)[0]
    assert ".panel,.demo-mode .panel{width:calc(100% - 24px);max-width:1280px" in coarse_css
    assert ".gen-btn{min-height:76px" in coarse_css
    assert ".mii-work-pet{left:max(calc(50% - 620px),28px);bottom:8px}" in coarse_css
