"""Upload and capture behaviour without a network or a screen:  python3 tests/test_agent.py"""
import os, sys, tempfile, threading, time, types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("mss", types.SimpleNamespace(mss=None))  # capture.py imports it; the test never grabs a screen
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from agent import capture, uploader  # noqa: E402
from agent.stats import Stats  # noqa: E402


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not ok:
        sys.exit(1)


class FakeS3:
    def __init__(self, delay=0.3, fail=False):
        self.puts, self.delay, self.fail, self.lock = [], delay, fail, threading.Lock()

    def put_object(self, **kw):
        if self.fail:
            raise OSError("network down")
        time.sleep(self.delay)
        with self.lock:
            self.puts.append(kw)


def run_uploader(files, cfg_extra, s3, seconds):
    spool = Path(tempfile.mkdtemp())
    now = time.time()
    for name, age in files:
        p = spool / name
        p.write_bytes(b"x" * 100)
        os.utime(p, (now - age, now - age))
    cfg = {"wasabi_access_key": "k", "wasabi_secret_key": "s", "wasabi_bucket": "b", "wasabi_endpoint": "http://x",
           "upload_workers": 4, "max_pending": 5, "max_age_seconds": 15, **cfg_extra}
    stats, stop = Stats(), threading.Event()
    u = uploader.Uploader(cfg, spool, stats, stop)
    u._client = s3
    u.start()
    time.sleep(seconds)
    stop.set()
    return spool, stats, s3


# 1. a backlog of 150 frames with a 0.3 s upload: only fresh ones are sent, the newest among them, the rest dropped
files = [(f"shot_20261112_120{i // 60}{i % 60:02d}_000.webp", 150 - i) for i in range(150)]  # 150 s old ... 1 s old
spool, stats, s3 = run_uploader(files, {}, FakeS3(), 2.5)
names = sorted(p["Key"].rsplit("/", 1)[1] for p in s3.puts)
snap = stats.snapshot()
check("stale backlog dropped, not uploaded", snap["dropped"] >= 140 and snap["uploaded"] <= 10, str((snap["dropped"], snap["uploaded"])))
check("only the newest frames were sent", names[0] >= files[-6][0], f"{names[0]} vs {files[-6][0]}")
check("key carries the capture day", "/2026/11/12/" in s3.puts[0]["Key"], s3.puts[0]["Key"])
check("metadata: queue time reported", all("queue-ms" in p["Metadata"] for p in s3.puts))

# 2. four at once beat one at a time
fresh = [(f"shot_20261112_120100_{i:03d}.webp", 1) for i in range(8)]
spool, stats, s3 = run_uploader(fresh, {"max_pending": 0}, FakeS3(0.5), 1.6)
check("8 files in parallel", len(s3.puts) == 8, str(len(s3.puts)))

# 3. network down: files that are still fresh stay, stale ones go, nothing crashes
spool, stats, s3 = run_uploader([("shot_20261112_120200_000.webp", 1), ("shot_20261112_120200_001.webp", 30)], {}, FakeS3(fail=True), 1.0)
left = sorted(p.name for p in spool.glob("shot_*"))
check("offline: fresh kept, stale dropped", left == ["shot_20261112_120200_000.webp"], str(left))

# 4. near-identical frames are skipped, a real change is sent, and a keepalive goes out
cap = capture.Capturer({"skip_unchanged": True, "keepalive_seconds": 0.4})
FONT = ImageFont.load_default(size=26)


def frame(text, cursor=False):
    im = Image.new("RGB", (1920, 1080), (30, 90, 40)); d = ImageDraw.Draw(im)
    d.rectangle([800, 500, 1100, 560], fill=(200, 200, 200)); d.text((820, 520), text, fill=(0, 0, 0), font=FONT)
    if cursor:
        d.rectangle([1200, 700, 1201, 714], fill=(255, 255, 255))  # a blinking text cursor
    return im


def feed(im):  # the skip decision grab() makes after taking the picture
    small = im.convert("L").resize(capture.SMALL)
    keep = cap.cfg["keepalive_seconds"]
    if cap._last_small is not None and not (keep and time.time() - cap._last_sent >= keep):
        diff = capture.ImageChops.difference(small, cap._last_small).point(lambda v: 255 if v > capture.LEVEL else 0)
        if diff.histogram()[255] < capture.PIXELS:
            return False
    cap._last_small = small; cap._last_sent = time.time(); return True


check("first frame sent", feed(frame("pot 1,200")))
check("blinking cursor only: skipped", not feed(frame("pot 1,200", cursor=True)))
check("one digit changed: sent", feed(frame("pot 1,300")))
time.sleep(0.5)
check("keepalive after the quiet spell", feed(frame("pot 1,300")))
print("all good")
