"""Grabs one screenshot and encodes it to bytes in memory."""
import io
import time

import mss
from PIL import Image, ImageChops

SMALL = (960, 540)   # frames are compared at this size (half of a 1080p screen)
PIXELS = 12          # fewer clearly changed pixels than this = unchanged. Measured on real table frames: a changed chip
                     # amount moves 47+ pixels, a clock tick or blinking cursor a handful
LEVEL = 16           # "clearly changed" = brighter or darker by more than this (of 255)


class Capturer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._last_small = None
        self._last_sent = 0.0
        self.last_ms = 0.0   # time spent grabbing and encoding the last frame

    def grab(self):
        """Return (bytes, ext). Returns (None, None) when the frame has not visibly changed since the last one
        sent (a clock or blinking cursor does not count) and skip_unchanged is on; a frame is still sent every
        keepalive_seconds so the server can tell the feed is alive."""
        t0 = time.time()
        cfg = self.cfg
        with mss.mss() as sct:
            idx = int(cfg.get("monitor", 0))
            # monitors[0] = every screen combined; [1] = primary; [2] = next...
            mon = sct.monitors[idx] if idx < len(sct.monitors) else sct.monitors[0]
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        scale = float(cfg.get("scale", 1.0) or 1.0)
        if scale != 1.0:
            img = img.resize(
                (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
            )

        if cfg.get("skip_unchanged", True):
            small = img.convert("L").resize(SMALL)
            keep = float(cfg.get("keepalive_seconds", 10) or 0)
            if self._last_small is not None and not (keep and time.time() - self._last_sent >= keep):
                diff = ImageChops.difference(small, self._last_small).point(lambda v: 255 if v > LEVEL else 0)
                if diff.histogram()[255] < PIXELS:
                    return None, None
            self._last_small = small
        self._last_sent = time.time()

        buf = io.BytesIO()
        fmt = str(cfg.get("image_format", "webp")).lower()
        q = int(cfg.get("quality", 60))
        if fmt == "jpeg":
            img.save(buf, "JPEG", quality=q)
            self.last_ms = (time.time() - t0) * 1000
            return buf.getvalue(), "jpg"
        img.save(buf, "WEBP", quality=q)
        self.last_ms = (time.time() - t0) * 1000
        return buf.getvalue(), "webp"
