"""Persistent settings for HOScrcpy — mirrors Java SettingUtil.

Config stored at ~/.hos-scrcpy/config.json

Schema:
{
    "remote_ips": ["192.168.1.100:8710", "192.168.1.101"],
    "use_video_stream": false,
    "default_port": "8710"
}
"""

import json
import os
import threading

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".hos-scrcpy")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

_lock = threading.Lock()
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _cache = {}
    return _cache


def _save(data: dict):
    global _cache
    _cache = data
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_remote_ips() -> list[str]:
    """Get persisted remote device IPs (with optional port)."""
    with _lock:
        return _load().get("remote_ips", [])


def add_remote_ip(ip: str) -> None:
    """Add a remote IP to the persisted list."""
    with _lock:
        data = _load()
        ips = data.get("remote_ips", [])
        if ip not in ips:
            ips.append(ip)
            data["remote_ips"] = ips
            _save(data)


def remove_remote_ip(ip: str) -> None:
    """Remove a remote IP from the persisted list."""
    with _lock:
        data = _load()
        ips = data.get("remote_ips", [])
        if ip in ips:
            ips.remove(ip)
            data["remote_ips"] = ips
            _save(data)


def get_setting(key: str, default=None):
    """Get a generic settings value by key."""
    with _lock:
        return _load().get(key, default)


def set_setting(key: str, value) -> None:
    """Set a generic settings value."""
    with _lock:
        data = _load()
        data[key] = value
        _save(data)


def get_use_video_stream() -> bool:
    """Get whether to prefer H.264 video stream over image mode."""
    return get_setting("use_video_stream", False)


def set_use_video_stream(enabled: bool) -> None:
    """Set video stream preference."""
    set_setting("use_video_stream", enabled)


def get_default_port() -> str:
    """Get the default hdc port."""
    return get_setting("default_port", "8710")
