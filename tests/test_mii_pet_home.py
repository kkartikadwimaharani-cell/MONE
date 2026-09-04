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
    assert 'preventDefault' not in javascript
    assert 'importantSelectors' in javascript

