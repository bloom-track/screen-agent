"""Background thread that uploads spooled screenshots straight to a Wasabi
(S3-compatible) bucket and deletes each local file once Wasabi confirms it.

The newest file goes first, several at once. A file that waits too long is
dropped (see max_pending / max_age_seconds): the screenshots feed a live
advisor, and a minutes-old screen is worse than none, because it also delays
every newer one. Failed uploads are retried with backoff while they are still
fresh. Object keys are grouped by machine and capture date:

    <prefix>/<hostname>/YYYY/MM/DD/shot_...webp

Old objects are removed by a bucket lifecycle rule, not by this app -- see
scripts/set_lifecycle.py. (Wasabi bills a 90-day minimum per object, so
deleting earlier saves nothing.)
"""
import re
import socket
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config as BotoConfig


class Uploader(threading.Thread):
    def __init__(self, cfg, spool, stats, stop_event, meta=None):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.spool = spool
        self.stats = stats
        self.stop_event = stop_event
        self.meta = meta if meta is not None else {}   # file name -> capture_ms, filled by the capture thread
        self.backoff = 1.0
        self.host = socket.gethostname()
        self._client = None
        self._puts = deque(maxlen=8)                    # recent upload durations, ms
        self.workers = max(1, int(cfg.get("upload_workers", 4)))

    def _ready(self) -> bool:
        return all(
            self.cfg.get(k)
            for k in ("wasabi_access_key", "wasabi_secret_key", "wasabi_bucket")
        )

    def _client_or_none(self):
        if self._client is not None:
            return self._client
        if not self._ready():
            self.stats.set_error("Configure Wasabi keys + bucket, then Start")
            return None
        self._client = boto3.client(
            "s3",
            endpoint_url=self.cfg["wasabi_endpoint"],
            aws_access_key_id=self.cfg["wasabi_access_key"],
            aws_secret_access_key=self.cfg["wasabi_secret_key"],
            region_name=self.cfg.get("wasabi_region", "us-east-1"),
            config=BotoConfig(retries={"max_attempts": 2}, connect_timeout=15,
                              read_timeout=30, max_pool_connections=self.workers + 2),
        )
        return self._client

    def _pending(self):
        return sorted(p for p in self.spool.glob("shot_*.*") if p.suffix != ".tmp")

    def _drop_stale(self, files):
        """Delete waiting files that are too old or beyond the newest max_pending. Returns what is left (oldest first)."""
        max_n = int(self.cfg.get("max_pending", 5) or 0)
        max_age = float(self.cfg.get("max_age_seconds", 15) or 0)
        keep, now = [], time.time()
        for f in files:
            try:
                age = now - f.stat().st_mtime
            except OSError:
                continue
            if max_age and age > max_age:
                self._drop(f)
            else:
                keep.append(f)
        if max_n and len(keep) > max_n:
            for f in keep[:-max_n]:
                self._drop(f)
            keep = keep[-max_n:]
        return keep

    def _drop(self, f):
        f.unlink(missing_ok=True)
        self.meta.pop(f.name, None)
        self.stats.inc("dropped")

    def run(self):
        pool = ThreadPoolExecutor(max_workers=self.workers)
        try:
            while not self.stop_event.is_set():
                client = self._client_or_none()
                if client is None:
                    self.stop_event.wait(2.0)
                    continue
                files = self._drop_stale(self._pending())
                if not files:
                    self.stop_event.wait(0.2)
                    continue
                batch = files[::-1][:self.workers]          # newest first
                results = list(pool.map(lambda f: self._upload_one(client, f), batch))
                if all(results):
                    self.backoff = 1.0
                elif not any(results):
                    self.stop_event.wait(self.backoff)       # everything failed: the network is down
                    self.backoff = min(self.backoff * 2, 30.0)
        finally:
            pool.shutdown(wait=False)

    def _object_key(self, f) -> str:
        prefix = str(self.cfg.get("key_prefix", "screenshots")).strip("/")
        m = re.match(r"shot_(\d{4})(\d{2})(\d{2})_", f.name)   # the day it was captured, not the day it got uploaded
        day = "/".join(m.groups()) if m else time.strftime("%Y/%m/%d")
        return f"{prefix}/{self.host}/{day}/{f.name}"

    def _upload_one(self, client, f) -> bool:
        try:
            data = f.read_bytes()
            md = {"queue-ms": str(int((time.time() - f.stat().st_mtime) * 1000))}   # waited on this laptop
            if f.name in self.meta:
                md["capture-ms"] = str(int(self.meta[f.name]))
            if self._puts:
                md["upload-ms"] = str(int(sorted(self._puts)[len(self._puts) // 2]))  # median of recent uploads
            t0 = time.time()
            client.put_object(
                Bucket=self.cfg["wasabi_bucket"],
                Key=self._object_key(f),
                Body=data,
                ContentType="image/" + f.suffix.lstrip("."),
                Metadata=md,
            )
            self._puts.append((time.time() - t0) * 1000)
            self.stats.inc("uploaded")
            self.stats.add_bytes(len(data))
            f.unlink(missing_ok=True)
            self.meta.pop(f.name, None)
            return True
        except Exception as e:  # network down, bad keys, bucket missing, etc.
            self.stats.set_error(str(e)[:200])
            return False
