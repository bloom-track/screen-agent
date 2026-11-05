"""Minimal test server so you can run the agent end-to-end today.

Replace this with an endpoint on your real backend. In production prefer
issuing a presigned S3/R2 URL per upload so storage keys never live in
the app; the client code only needs the POST target to change.

Run:  pip install flask && python server/server.py
"""
import time
from pathlib import Path

from flask import Flask, request

app = Flask(__name__)
STORE = Path("uploads")
STORE.mkdir(exist_ok=True)

# Set a token to require "Authorization: Bearer <token>"; "" disables the check.
API_KEY = ""


@app.post("/api/screenshots")
def screenshots():
    if API_KEY and request.headers.get("Authorization") != "Bearer " + API_KEY:
        return {"error": "unauthorized"}, 401
    f = request.files.get("file")
    if not f:
        return {"error": "no file"}, 400
    dest = STORE / f"{int(time.time() * 1000)}_{f.filename}"
    f.save(dest)
    return {"ok": True, "saved": dest.name, "bytes": dest.stat().st_size}, 201


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
