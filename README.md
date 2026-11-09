# Screen Agent

A tiny Windows app that captures a screenshot every few seconds and uploads it
to cloud storage, with a one-click **Start / Stop** and live stats. Pure Python
+ Tkinter, so the installer stays small and there's nothing extra to install.

**Download:** https://bloom-track.github.io/screen-agent

---

## Features

- One screenshot every N seconds (default 3), uploaded automatically
- **Start / Stop** with live stats: captured, uploaded, pending, bandwidth, uptime
- **View latest capture** opens your most recent screenshot in the browser
- Disk-backed upload queue — survives offline periods and reboots, retries with backoff
- Uploads straight to **Wasabi** (S3-compatible); objects grouped by machine and date
- Optional auto-start on sign-in; clean installer + uninstaller
- Skips frames identical to the previous one (idle screen) to save bandwidth

## For users (install)

1. Open the **[download page](https://bloom-track.github.io/screen-agent)** and click **Download for Windows**.
2. If Windows shows “Windows protected your PC”, click **More info → Run anyway** (the app isn’t code-signed yet).
3. Run the installer, launch **Screen Agent**, fill in the bucket + keys if they aren’t pre-set, and press **Start**.

Requires Windows 10 or 11 (64-bit). Windows needs no screen-recording permission.

## Layout

```
agent/
  app.py        Tkinter window + Start/Stop + the capture worker
  capture.py    grab one screenshot -> WebP/JPEG bytes
  uploader.py   background thread: upload to Wasabi + disk-backed retry queue
  stats.py      thread-safe counters for the live display
  config.py     settings + where files live
scripts/
  set_lifecycle.py   one-time: auto-delete old screenshots after 90 days
installer/
  screen-agent.iss   Inno Setup installer script
docs/
  index.html         the download page (served by GitHub Pages)
```

## For developers

### Run it (Mac or Windows)

```bash
cd screen-agent
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python agent/app.py
```

On macOS the first run asks for Screen Recording permission (System Settings →
Privacy). On Windows there is no such prompt.

### Build the Windows .exe + installer

Pushing to `main` runs `.github/workflows/build-windows.yml`, which builds the
exe and the Inno Setup installer and publishes them as a GitHub release. The
download page always links to the latest release.

To build locally on Windows:

```bat
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name ScreenAgent --hidden-import PIL._tkinter_finder agent/app.py
iscc installer\screen-agent.iss
```

### Pre-load credentials (optional)

Add repo **Actions secrets** `WASABI_ACCESS_KEY` and `WASABI_SECRET_KEY`; the
build bakes them into the installer so the app works with no setup. Use a
**put-only key scoped to the bucket** — never a production key — because anyone
can download a public installer and extract what’s baked in.

## Configuration

Stored at `%LOCALAPPDATA%\ScreenAgent\config.json` (the upload queue is the
`spool` folder beside it). Editable in the window: bucket, region, keys, interval.

| Key | Default | Notes |
|---|---|---|
| `wasabi_bucket` / `wasabi_region` / `wasabi_endpoint` | `pranayapp` / `ap-southeast-1` / Singapore | target bucket |
| `interval_seconds` | `3` | seconds between captures |
| `quality` | `60` | WebP/JPEG quality 1–100 |
| `scale` | `1.0` | `0.5` = half resolution, saves bandwidth |
| `monitor` | `0` | `0` = all screens, `1` = primary only |
| `skip_unchanged` | `true` | drop frames identical to the previous one |

At one shot / 3s that’s roughly 150 MB/hour/machine before skipping, so plan
retention. Wasabi bills a **90-day minimum per object**, so clean up with a
bucket lifecycle rule (`scripts/set_lifecycle.py`), not per-run deletion.

## Known gotchas

- **Clock skew:** Wasabi/S3 reject uploads if the machine clock is off by >15 min
  (`RequestTimeTooSkewed`). Fix the OS time (enable automatic time sync), not the app.
- **macOS** silently drops other apps’ windows without Screen Recording permission.
- **Unsigned:** Windows SmartScreen and some antivirus warn on an unsigned
  cloud-uploading app. Code signing (e.g. Azure Trusted Signing) removes the warning.

## Not included (yet)

- Code signing
- System-tray minimize instead of a window
- At-rest encryption of spooled frames
