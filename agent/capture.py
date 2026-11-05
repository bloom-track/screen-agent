"""Grabs one screenshot and encodes it to bytes in memory."""
import hashlib
import io

import mss
from PIL import Image


class Capturer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._last_hash = None

    def grab(self):
        """Return (bytes, ext). Returns (None, None) when the frame is
        identical to the previous one and skip_unchanged is on."""
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
            h = hashlib.md5(img.tobytes()).hexdigest()
            if h == self._last_hash:
                return None, None
            self._last_hash = h

        buf = io.BytesIO()
        fmt = str(cfg.get("image_format", "webp")).lower()
        q = int(cfg.get("quality", 60))
        if fmt == "jpeg":
            img.save(buf, "JPEG", quality=q)
            return buf.getvalue(), "jpg"
        img.save(buf, "WEBP", quality=q)
        return buf.getvalue(), "webp"
