from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO = (ROOT / "templates" / "ai-video.html").read_text()
HOME = (ROOT / "templates" / "index.html").read_text()


def test_public_demo_copy_and_home_card_are_exact_and_unique():
    assert "JELAJAHI WORKSPACE MII AI VIDEO" in DEMO
    assert "VERSI DEMO INI HANYA UNTUK EKSPLORASI DAN TIDAK MENJALANKAN GENERASI ATAU MENGGUNAKAN KREDIT." in DEMO
    assert HOME.count("MII AI VIDEO · PUBLIC DEMO") == 1
    assert "COBA LANGSUNG TAMPILAN WORKSPACE DAN JELAJAHI MODEL, MODE, SERTA KONTROL YANG TERSEDIA. AMAN UNTUK DICOBA TANPA MENJALANKAN GENERASI." in HOME
    assert 'href="/mii-ai-video"' in HOME


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
