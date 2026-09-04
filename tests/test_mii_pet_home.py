from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def test_home_sprite_contract():
    sprite = ROOT / 'static/pet/chibi-makima/home-spritesheet.png'
    with Image.open(sprite) as image:
        assert image.mode == 'RGBA'
        assert image.size == (1536, 1872)


def test_pet_modules_are_lightweight_and_scoped():
    pet_dir = ROOT / 'static/js/mii-pet'
    javascript = '\n'.join(path.read_text() for path in pet_dir.glob('*.js'))
    assert 'visibilitychange' in javascript
    assert 'MutationObserver' not in javascript
    assert 'pointerdown' in javascript
    assert javascript.count('preventDefault') == 1
    assert "target.pathname !== '/ai-video'" in javascript
    assert 'importantSelectors' in javascript


def test_ai_video_navigation_uses_a_scoped_exit_transition():
    engine = (ROOT / 'static/js/mii-pet/engine.js').read_text()

    assert "sessionStorage.setItem('mii-pet-page-transition'" in engine
    assert 'window.location.assign(url)' in engine
