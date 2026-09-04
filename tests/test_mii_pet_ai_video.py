from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ai_video_pet_is_isolated_and_lightweight():
    controller = (ROOT / 'static/js/mii-pet/ai-video-controller.js').read_text()
    css = (ROOT / 'static/css/mii-pet-ai-video.css').read_text()

    assert "mii-pet:generation" in controller
    assert 'MutationObserver' not in controller
    assert 'preventDefault' not in controller
    assert 'visibilitychange' in controller
    assert 'pointer-events: none' in css


def test_ai_video_uses_page_specific_asset():
    config = (ROOT / 'static/js/mii-pet/ai-video-config.js').read_text()
    css = (ROOT / 'static/css/mii-pet-ai-video.css').read_text()

    assert 'home-spritesheet' not in css
    assert 'ai-video-spritesheet.png' in css
    for state in ('idle', 'waiting', 'working', 'review', 'failed'):
        assert f'{state}:' in config


def test_ai_video_consumes_home_transition_once():
    bootstrap = (ROOT / 'static/js/mii-pet/ai-video-bootstrap.js').read_text()

    assert "sessionStorage.getItem('mii-pet-page-transition')" in bootstrap
    assert "sessionStorage.removeItem('mii-pet-page-transition')" in bootstrap
    assert 'mii-work-pet--entering' in bootstrap
