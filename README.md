# Screen Agent

A tiny Windows app: **Start/Stop**, screenshot every N seconds, upload straight
to a **Wasabi** (S3-compatible) bucket, live stats (captured, uploaded, pending,
bandwidth). Pure Python + Tkinter + boto3, so the `.exe` stays small.

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
server/
  server.py     optional local test endpoint (not used with Wasabi)
```

## Configure (keys in the app)

Open the app and fill in **Bucket, Region, Access key, Secret key**, then
**Start**. Values are saved to `%LOCALAPPDATA%\ScreenAgent\config.json`.

> Keys live on each machine running the app. Scope the Wasabi access key to
> **put-only on this one bucket** so a leaked key can't read or delete anything.

Region → endpoint must match, e.g.:

| Region | Endpoint |
|---|---|
| `us-east-1` | `https://s3.us-east-1.wasabisys.com` |
| `ap-southeast-1` | `https://s3.ap-southeast-1.wasabisys.com` |

Set the endpoint in `config.json` (`wasabi_endpoint`) if your bucket isn't in
`us-east-1`. Objects are stored as
`screenshots/<hostname>/YYYY/MM/DD/shot_...webp`.

## Auto-delete old screenshots

Wasabi bills a **90-day minimum per object**, so deleting earlier saves nothing.
Set a bucket lifecycle rule once instead of deleting from the app:

```bash
pip install boto3
python scripts/set_lifecycle.py          # delete after 90 days
python scripts/set_lifecycle.py --days 120
```

## Run it in dev (Mac or Windows)

```bash
cd screen-agent
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python agent/app.py
```

On macOS the first run asks for Screen Recording permission (System Settings →
Privacy).

## Build the Windows .exe

You're on a Mac, so build on a Windows runner. Push this repo to GitHub and the
workflow (`.github/workflows/build-windows.yml`) produces `ScreenAgent.exe` as a
downloadable artifact on every push — get it from the Actions tab. That single
file is the whole app; double-click to run.

**Zero-typing build (keys baked in, not committed):** in the GitHub repo add two
Actions secrets — Settings → Secrets and variables → Actions:

- `WASABI_ACCESS_KEY`
- `WASABI_SECRET_KEY`

The build writes them into `bundled_config.json` inside the exe (bucket/region
are already set to `pranayapp` / `ap-southeast-1`). The shipped exe then uploads
with no setup. A per-machine `%LOCALAPPDATA%\ScreenAgent\config.json` still
overrides the baked values if you ever need to. The keys never enter git.

On an actual Windows machine instead:

```bat
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name ScreenAgent --hidden-import PIL._tkinter_finder agent/app.py
```

## Tuning (config.json)

- **scale** `0.5` + **quality** `60` roughly quarter the bandwidth.
- **skip_unchanged** drops frames identical to the previous one (idle screen).
- **monitor** `0` = all screens, `1` = primary only.
- At one shot / 3s that's ~150 MB/hr/machine before skip — retention matters.

## Not included (ask if you want them)

- A real installer with Start-menu entry + auto-start on login (Inno Setup).
- System-tray minimize instead of a window (pystray).
- Code signing (needed to avoid the Windows SmartScreen warning).
