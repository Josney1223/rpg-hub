"""Config locations and small JSON persistence helpers.

Paths are module-level names so tests can point them at a temp dir.
Always read them as ``config.NAME`` (not ``from config import NAME``) so an
override at runtime is picked up.
"""

import os
import sys
import json


def default_config_dir():
    """Per-OS config location: %APPDATA% on Windows, ~/.config elsewhere."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "MothershipLights")
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(xdg, "mothership_lights")


CONFIG_DIR = default_config_dir()
DEVICES_FILE = os.path.join(CONFIG_DIR, "devices.json")
PLAYLISTS_FILE = os.path.join(CONFIG_DIR, "playlists.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
COLORS_FILE = os.path.join(CONFIG_DIR, "colors.json")
PACKS_DIR = os.path.join(CONFIG_DIR, "packs")

DEFAULT_SETTINGS = {
    "backend": "tuya",                      # "tuya" (direct) or "ha" (Home Assistant)
    "ha_url": "http://localhost:8123",
    "ha_token": "",
}


def load_json(path, default):
    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    s.update(load_json(SETTINGS_FILE, {}) or {})
    return s


def save_settings(settings):
    save_json(SETTINGS_FILE, settings)
