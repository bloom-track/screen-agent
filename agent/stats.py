"""Thread-safe counters shared between the capture thread, the upload
thread, and the GUI."""
import threading
import time


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self.captured = 0
            self.skipped = 0
            self.uploaded = 0
            self.bytes_uploaded = 0
            self.started_at = None
            self.ended_at = None
            self.last_error = ""

    def start_session(self):
        with self.lock:
            self.started_at = time.time()
            self.ended_at = None

    def stop_session(self):
        with self.lock:
            if self.started_at and not self.ended_at:
                self.ended_at = time.time()

    def inc(self, field: str, n: int = 1):
        with self.lock:
            setattr(self, field, getattr(self, field) + n)

    def add_bytes(self, n: int):
        with self.lock:
            self.bytes_uploaded += n

    def set_error(self, msg: str):
        with self.lock:
            self.last_error = msg

    def snapshot(self) -> dict:
        with self.lock:
            end = self.ended_at or time.time()
            uptime = (end - self.started_at) if self.started_at else 0.0
            return {
                "captured": self.captured,
                "skipped": self.skipped,
                "uploaded": self.uploaded,
                "bytes_uploaded": self.bytes_uploaded,
                "last_error": self.last_error,
                "uptime": uptime,
            }
