"""Screen Agent - a tiny Windows tray-style app.

One window: Start / Stop and live stats (captured, uploaded, pending,
bandwidth). It captures one screenshot every few seconds, spools it to
disk, and a background thread uploads it to your server.

Run in dev:   python agent/app.py
Build .exe:   see README.md
"""
import socket
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import ttk

import boto3

import config
from capture import Capturer
from stats import Stats
from uploader import Uploader


class CaptureWorker(threading.Thread):
    def __init__(self, cfg, spool, stats, stop_event, meta=None):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.spool = spool
        self.stats = stats
        self.stop_event = stop_event
        self.meta = meta if meta is not None else {}
        self.capturer = Capturer(cfg)

    def run(self):
        interval = float(self.cfg.get("interval_seconds", 3.0))
        while not self.stop_event.is_set():
            t0 = time.time()
            try:
                data, ext = self.capturer.grab()
                if data is None:
                    self.stats.inc("skipped")
                else:
                    self._write(data, ext)
                    self.stats.inc("captured")
            except Exception as e:
                self.stats.set_error("capture: " + str(e)[:150])
            # keep a steady cadence regardless of how long the grab took
            self.stop_event.wait(max(0.0, interval - (time.time() - t0)))

    def _write(self, data, ext):
        ts = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        final = self.spool / f"shot_{ts}.{ext}"
        tmp = final.with_suffix(final.suffix + ".tmp")
        tmp.write_bytes(data)              # write fully, then rename so the
        tmp.rename(final)                 # uploader never sees a half file
        self.meta[final.name] = self.capturer.last_ms


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Screen Agent")
        self.geometry("400x620")
        self.resizable(False, False)

        self.cfg = config.load()
        self.spool = config.spool_dir()
        self.stats = Stats()
        self.stop_event = None
        self.running = False

        self._build_ui()
        self._tick()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- UI -------------------------------------------------------------
    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        self.fields = {}
        rows_cfg = [
            ("wasabi_bucket", "Bucket", False),
            ("wasabi_region", "Region", False),
            ("wasabi_access_key", "Access key", False),
            ("wasabi_secret_key", "Secret key", True),
        ]
        for i, (key, label, secret) in enumerate(rows_cfg):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", **pad)
            var = tk.StringVar(value=str(self.cfg.get(key, "")))
            self.fields[key] = var
            ttk.Entry(frm, textvariable=var, width=34,
                      show="*" if secret else "").grid(row=i, column=1, **pad)

        ttk.Label(frm, text="Interval (sec)").grid(row=4, column=0, sticky="w", **pad)
        self.interval_var = tk.StringVar(value=str(self.cfg["interval_seconds"]))
        ttk.Entry(frm, textvariable=self.interval_var, width=8).grid(
            row=4, column=1, sticky="w", **pad
        )

        btns = tk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=12)
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)
        self.start_btn = tk.Button(
            btns, text="▶  Start", command=self._start,
            bg="#27ae60", fg="white", font=("", 13, "bold"), height=2,
            relief="flat", activebackground="#1e8449", disabledforeground="#eafaf1",
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.stop_btn = tk.Button(
            btns, text="■  Stop", command=self._stop,
            bg="#e74c3c", fg="white", font=("", 13, "bold"), height=2,
            relief="flat", activebackground="#c0392b", state="disabled",
            disabledforeground="#f5b7b1",
        )
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        box = ttk.LabelFrame(frm, text="Live stats")
        box.grid(row=6, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
        self.stat_vars = {}
        rows = [
            ("status", "Status"), ("captured", "Captured"), ("uploaded", "Uploaded"),
            ("pending", "Pending"), ("dropped", "Dropped (stale)"), ("bandwidth", "Bandwidth"),
            ("rate", "Upload rate"), ("uptime", "Uptime"),
        ]
        for i, (key, label) in enumerate(rows):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="w", padx=10, pady=2)
            v = tk.StringVar(value="-")
            self.stat_vars[key] = v
            ttk.Label(box, textvariable=v, font=("", 10, "bold")).grid(
                row=i, column=1, sticky="w", padx=10, pady=2
            )

        self.view_btn = tk.Button(
            frm, text="\U0001f50d  View latest capture", command=self._view_latest,
            relief="flat",
        )
        self.view_btn.grid(row=7, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 2))

        self.clear_btn = tk.Button(
            frm, text="\U0001f5d1  Clear pending uploads", command=self._clear_pending,
            relief="flat",
        )
        self.clear_btn.grid(row=9, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 2))

        self.err_var = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.err_var, foreground="#c0392b",
                  wraplength=360).grid(row=10, column=0, columnspan=2, padx=12)

    # ---- actions --------------------------------------------------------
    def _save_settings(self):
        for key, var in self.fields.items():
            self.cfg[key] = var.get().strip()
        try:
            self.cfg["interval_seconds"] = float(self.interval_var.get())
        except ValueError:
            self.cfg["interval_seconds"] = 3.0
        config.save(self.cfg)

    def _start(self):
        if self.running:
            return
        self._save_settings()
        self.stats.reset()
        self.stats.start_session()
        self.stop_event = threading.Event()
        meta = {}
        workers = [
            CaptureWorker(self.cfg, self.spool, self.stats, self.stop_event, meta),
            Uploader(self.cfg, self.spool, self.stats, self.stop_event, meta),
        ]
        for w in workers:
            w.start()
        self.running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def _stop(self):
        if self.stop_event:
            self.stop_event.set()
        self.stats.stop_session()
        self.running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def _clear_pending(self):
        """Delete every screenshot still waiting to upload (they are stale for live advice)."""
        n = 0
        for p in self.spool.glob("shot_*.*"):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
        self.stats.inc("dropped", n)
        self.stats.set_error(f"Cleared {n} pending uploads")

    def _view_latest(self):
        """Find the newest screenshot for this machine in Wasabi and open it
        in the browser via a short-lived presigned URL. Runs off the UI
        thread so the window never freezes on the network call."""
        self._save_settings()

        def work():
            c = self.cfg
            if not (c.get("wasabi_access_key") and c.get("wasabi_bucket")):
                self.stats.set_error("Configure Wasabi keys first")
                return
            try:
                s3 = boto3.client(
                    "s3", endpoint_url=c["wasabi_endpoint"],
                    aws_access_key_id=c["wasabi_access_key"],
                    aws_secret_access_key=c["wasabi_secret_key"],
                    region_name=c.get("wasabi_region", "us-east-1"),
                )
                prefix = (str(c.get("key_prefix", "screenshots")).strip("/")
                          + "/" + socket.gethostname() + "/")
                latest = None
                for page in s3.get_paginator("list_objects_v2").paginate(
                        Bucket=c["wasabi_bucket"], Prefix=prefix):
                    for o in page.get("Contents", []):
                        if latest is None or o["LastModified"] > latest["LastModified"]:
                            latest = o
                if not latest:
                    self.stats.set_error("No screenshots uploaded yet")
                    return
                url = s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": c["wasabi_bucket"], "Key": latest["Key"]},
                    ExpiresIn=3600,
                )
                webbrowser.open(url)
                self.stats.set_error("")
            except Exception as e:
                self.stats.set_error(str(e)[:200])

        threading.Thread(target=work, daemon=True).start()

    def _tick(self):
        s = self.stats.snapshot()
        pending = len([p for p in self.spool.glob("shot_*.*") if p.suffix != ".tmp"])
        up = s["uptime"]
        mb = s["bytes_uploaded"]
        rate = (mb / up * 60) if up > 0 else 0  # bytes per minute

        self.stat_vars["status"].set("Running" if self.running else "Stopped")
        self.stat_vars["captured"].set(f"{s['captured']}  (skipped {s['skipped']})")
        self.stat_vars["uploaded"].set(str(s["uploaded"]))
        self.stat_vars["pending"].set(str(pending))
        self.stat_vars["dropped"].set(str(s["dropped"]))
        self.stat_vars["bandwidth"].set(human_bytes(mb))
        self.stat_vars["rate"].set(human_bytes(rate) + "/min")
        self.stat_vars["uptime"].set(time.strftime("%H:%M:%S", time.gmtime(up)))
        self.err_var.set(s["last_error"])
        self.after(1000, self._tick)

    def _on_close(self):
        self._stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
