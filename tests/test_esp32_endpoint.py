"""
Tests for the ESP32 image data endpoint (/api/esp32/image_data).

Uses a Flask test client with a lightweight mock device config so no
hardware or heavy dependencies are needed.
"""

import io
import math
import os
import sys
import pytest

# Make the src package importable without installing it
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flask import Flask
from blueprints.main import main_bp


# ---------------------------------------------------------------------------
# Minimal stub for Config so we don't need the full device.json
# ---------------------------------------------------------------------------

class _FakeConfig:
    def get_config(self, key=None, default={}):
        return default if key else {}

    def get_plugins(self):
        return []


# ---------------------------------------------------------------------------
# Flask app fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path):
    """Create a minimal Flask app with only the main blueprint registered."""
    application = Flask(__name__, static_folder=None)
    application.config['DEVICE_CONFIG'] = _FakeConfig()
    application.config['TESTING'] = True
    application.register_blueprint(main_bp)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Helper: write a small PNG to the path InkyPi uses for the current image
# ---------------------------------------------------------------------------

def _write_current_image(src_dir, width=10, height=10):
    """Create a tiny white PNG at the path the endpoint reads from."""
    from PIL import Image

    images_dir = os.path.join(src_dir, 'static', 'images')
    os.makedirs(images_dir, exist_ok=True)
    img_path = os.path.join(images_dir, 'current_image.png')
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    img.save(img_path)
    return img_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEsp32ImageDataEndpoint:

    def test_returns_404_when_no_image(self, client):
        """Endpoint returns 404 when current_image.png does not exist."""
        response = client.get('/api/esp32/image_data?display_type=epd2in13v2')
        assert response.status_code == 404

    def test_returns_400_without_params(self, client, monkeypatch, tmp_path):
        """Endpoint returns 400 when neither display_type nor width/height is given."""
        img_path = _write_current_image(str(tmp_path))
        # Patch the endpoint to look in tmp_path for the image
        import blueprints.main as main_module
        monkeypatch.setattr(main_module, '__file__',
                            os.path.join(str(tmp_path), 'blueprints', 'main.py'))
        response = client.get('/api/esp32/image_data')
        assert response.status_code == 400

    @pytest.mark.parametrize("display_type,expected_w,expected_h", [
        ("epd2in13v2", 250, 122),
        ("epd2in9v2",  296, 128),
        ("epd4in2",    400, 300),
    ])
    def test_known_display_type_returns_correct_size(
        self, client, monkeypatch, tmp_path,
        display_type, expected_w, expected_h
    ):
        """
        Endpoint returns the right number of bytes for each known display type
        and echoes dimensions in response headers.
        """
        _write_current_image(str(tmp_path), width=100, height=100)

        # Make the endpoint resolve the image from tmp_path
        import blueprints.main as main_module
        monkeypatch.setattr(
            main_module, '__file__',
            os.path.join(str(tmp_path), 'blueprints', 'main.py'),
        )

        response = client.get(f'/api/esp32/image_data?display_type={display_type}')
        assert response.status_code == 200
        assert response.content_type == 'application/octet-stream'

        assert int(response.headers['X-Width'])  == expected_w
        assert int(response.headers['X-Height']) == expected_h

        expected_bytes = math.ceil(expected_w / 8) * expected_h
        assert len(response.data) == expected_bytes

    def test_explicit_width_height(self, client, monkeypatch, tmp_path):
        """Endpoint respects explicit width and height query params."""
        _write_current_image(str(tmp_path), width=50, height=50)

        import blueprints.main as main_module
        monkeypatch.setattr(
            main_module, '__file__',
            os.path.join(str(tmp_path), 'blueprints', 'main.py'),
        )

        response = client.get('/api/esp32/image_data?width=32&height=24')
        assert response.status_code == 200
        expected_bytes = math.ceil(32 / 8) * 24  # 4 * 24 = 96
        assert len(response.data) == expected_bytes
        assert int(response.headers['X-Width'])  == 32
        assert int(response.headers['X-Height']) == 24

    def test_white_image_produces_all_set_bits(self, client, monkeypatch, tmp_path):
        """A pure-white source image must result in all bytes == 0xFF (all white)."""
        _write_current_image(str(tmp_path), width=8, height=4)

        import blueprints.main as main_module
        monkeypatch.setattr(
            main_module, '__file__',
            os.path.join(str(tmp_path), 'blueprints', 'main.py'),
        )

        response = client.get('/api/esp32/image_data?width=8&height=4')
        assert response.status_code == 200
        # 8-wide display → 1 byte per row, 4 rows → 4 bytes, all 0xFF
        assert response.data == bytes([0xFF] * 4)

    def test_cache_control_header(self, client, monkeypatch, tmp_path):
        """Response must carry Cache-Control: no-cache."""
        _write_current_image(str(tmp_path))

        import blueprints.main as main_module
        monkeypatch.setattr(
            main_module, '__file__',
            os.path.join(str(tmp_path), 'blueprints', 'main.py'),
        )

        response = client.get('/api/esp32/image_data?display_type=epd2in13v2')
        assert response.status_code == 200
        assert 'no-cache' in response.headers.get('Cache-Control', '')
