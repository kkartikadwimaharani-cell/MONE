from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_maintenance_template_is_native_and_keeps_existing_pet():
    template = (ROOT / 'templates/maintenance.html').read_text()

    assert 'maintenance-sleep-strip.png' not in template
    assert 'maintenance-sleep-pet__sprite' in template
    assert 'maintenance-progress' not in template
    assert 'maintenance-wave' not in template
    assert 'maintenance-sleep-pet__eye' not in template
    assert 'maintenance-card' in template
    assert template.index('maintenance-card') < template.index('maintenance-brand')
    assert 'maintenance-makima-bg.webp' not in template
    assert 'PLEASE WAIT A LITTLE LONGER.' in template
    assert 'Makima is currently resting' not in template
    assert "asset_url('js/mii-pet/maintenance-pet.js')" in template


def test_maintenance_pet_uses_one_reset_timer_and_no_frame_loop():
    script = (ROOT / 'static/js/mii-pet/maintenance-pet.js').read_text()

    for state in ('sleep', 'disturbed', 'annoyed', 'bonk'):
        assert state in script
    assert 'peek' not in script
    assert script.count('let resetTimer') == 1
    assert 'setInterval' not in script
    assert 'requestAnimationFrame' not in script
    assert 'visibilitychange' in script
    assert 'window.location' not in script


def test_maintenance_visuals_are_css_driven_and_scoped():
    base_css = (ROOT / 'static/css/maintenance.css').read_text()
    pet_css = (ROOT / 'static/css/maintenance-pet.css').read_text()

    assert 'maintenanceStatusPulse' in base_css
    assert 'maintenanceAmbient' in base_css
    assert 'maintenanceTitlePulse' in base_css
    assert 'maintenancePanelScan' in base_css
    assert "url('/static/images/maintenance-makima-bg.webp')" in base_css
    assert 'maintenanceScreenBonk 68ms' in base_css
    assert '(min-width: 880px) and (max-height: 850px)' in base_css
    assert 'maintenancePetDream 2.1s' in pet_css
    assert "url('/static/pet/chibi-makima/maintenance-sleep-strip.png')" in pet_css
    assert 'canvas' not in (base_css + pet_css).lower()
    assert 'webgl' not in (base_css + pet_css).lower()
    assert 'maintenance-sleep-pet__eye' not in pet_css


def test_generated_maintenance_background_is_small_and_local():
    artwork = ROOT / 'static/images/maintenance-makima-bg.webp'

    assert artwork.exists()
    assert artwork.stat().st_size < 100_000
