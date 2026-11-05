"""Background thread that uploads spooled screenshots straight to a Wasabi
(S3-compatible) bucket and deletes each local file once Wasabi confirms it.

Files that fail to upload stay on disk and are retried with exponential
backoff, so a dropped connection or a reboot never loses captures. Object
keys are grouped by machine and date:

    <prefix>/<hostname>/YYYY/MM/DD/shot_...webp

Old objects are removed by a bucket lifecycle rule, not by this app -- see
scripts/set_lifecycle.py. (Wasabi bills a 90-day minimum per object, so
deleting earlier saves nothing.)
"""
import socket
import threading
import time

import boto3
from botocore.config import Config as BotoConfig


class Uploader(threading.Thread):
    def __init__(self, cfg, spool, stats, stop_event):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.spool = spool
        self.stats = stats
        self.stop_event = stop_event
        self.backoff = 1.0
        self.host = socket.gethostname()
        self._client = None

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
                              read_timeout=30),
        )
        return self._client

    def _pending(self):
        return sorted(p for p in self.spool.glob("shot_*.*") if p.suffix != ".tmp")

    def run(self):
        while not self.stop_event.is_set():
            client = self._client_or_none()
            if client is None:
                self.stop_event.wait(2.0)
                continue
            files = self._pending()
            if not files:
                self.stop_event.wait(1.0)
                continue
            for f in files:
                if self.stop_event.is_set():
                    break
                if self._upload_one(client, f):
                    self.backoff = 1.0
                else:
                    self.stop_event.wait(self.backoff)
                    self.backoff = min(self.backoff * 2, 30.0)
                    break  # restart the batch after backing off

    def _object_key(self, f) -> str:
        prefix = str(self.cfg.get("key_prefix", "screenshots")).strip("/")
        day = time.strftime("%Y/%m/%d")
        return f"{prefix}/{self.host}/{day}/{f.name}"

    def _upload_one(self, client, f) -> bool:
        try:
            data = f.read_bytes()
            client.put_object(
                Bucket=self.cfg["wasabi_bucket"],
                Key=self._object_key(f),
                Body=data,
                ContentType="image/" + f.suffix.lstrip("."),
            )
            self.stats.inc("uploaded")
            self.stats.add_bytes(len(data))
            f.unlink(missing_ok=True)
            return True
        except Exception as e:  # network down, bad keys, bucket missing, etc.
            self.stats.set_error(str(e)[:200])
            return False
