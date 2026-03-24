"""
config_manager.py – Config persistence for InkyPi ESP32.

Reads and writes a JSON config file stored on the ESP32 flash filesystem.
Falls back to defaults when the file is missing or corrupt.
"""

import json

CONFIG_FILE = "config.json"

DEFAULTS = {
    "wifi_ssid": "",
    "wifi_password": "",
    "inkypi_url": "http://inkypi.local",
    "display_type": "epd2in13v2",
    "refresh_interval": 300,
    "ap_ssid": "InkyPi-ESP32",
    "ap_password": "inkypi123",
    "rotation": 0,
}


def load():
    """Load config from flash. Returns a dict with defaults merged in."""
    config = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE) as f:
            stored = json.load(f)
        config.update(stored)
    except (OSError, ValueError):
        pass
    return config


def save(config):
    """Persist config dict to flash."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)


def update(key, value):
    """Update a single key and persist."""
    config = load()
    config[key] = value
    save(config)
