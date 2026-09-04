from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_maintenance_pet_stays_minimal():
    css = (ROOT / 'static/css/maintenance-pet.css').read_text()
    script = (ROOT / 'static/js/mii-pet/maintenance-pet.js').read_text()

    assert 'maintenance-sleep-strip.png' in css
    assert 'maintenancePetSleep' in css
    assert 'maintenancePetDream' in css
    assert 'pointer-events: none' in css
    assert 'visibilitychange' in script
    assert 'MutationObserver' not in script
    assert 'setInterval' not in script
    assert 'setTimeout' not in script
