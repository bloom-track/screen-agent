"""Settings + where files live. Config and the upload spool live under
%LOCALAPPDATA%\\ScreenAgent on Windows (falls back to ~ for Mac dev).

Uploads go straight to a Wasabi (S3-compatible) bucket. The access/secret
keys live here in config.json on the machine running the app."""
import json
import os
import sys
from pathlib import Path

APP_NAME = "ScreenAgent"

DEFAULTS = {
    # --- Wasabi bucket ---
    "wasabi_access_key": "",       # filled on the machine, not committed
    "wasabi_secret_key": "",       # filled on the machine, not committed
    "wasabi_bucket": "pranayapp",
    "wasabi_region": "ap-southeast-1",
    "wasabi_endpoint": "https://s3.ap-southeast-1.wasabisys.com",
    "key_prefix": "screenshots",   # folder inside the bucket
    # --- capture ---
    "interval_seconds": 3.0,       # one screenshot every N seconds
    "image_format": "webp",        # webp (smaller) | jpeg
    "quality": 60,                 # 1-100
    "scale": 1.0,                  # 0.5 = half resolution, saves bandwidth
    "monitor": 0,                  # 0 = all screens, 1 = primary, 2 = second...
    "skip_unchanged": True,        # skip a frame that has not visibly changed since the last one sent
    "keepalive_seconds": 10,       # ...but still send one at least this often, so the server knows the feed is alive
    # --- upload ---
    "upload_workers": 4,           # files uploaded at the same time
    "max_pending": 5,              # keep only the newest N waiting files; older ones are stale for live advice (0 = keep all)
    "max_age_seconds": 15,         # a waiting file older than this is dropped (0 = never)
}


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return data_dir() / "config.json"


def spool_dir() -> Path:
    d = data_dir() / "spool"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bundled() -> dict:
    """Config baked into the .exe at build time (keys from GitHub Secrets).
    Lives in the PyInstaller bundle, never in the git repo."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return {}
    p = Path(base) / "bundled_config.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def load() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(_bundled())            # baked-in keys, if built with them
    p = config_path()
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text()))   # per-machine overrides win
        except Exception:
            pass  # corrupt config -> fall back to defaults + bundled
    return cfg


def save(cfg: dict) -> None:
    config_path().write_text(json.dumps(cfg, indent=2))
