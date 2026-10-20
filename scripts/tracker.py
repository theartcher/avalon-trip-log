"""Always-on Avalon tracker for a Raspberry Pi (or any always-on Linux box).

Stays connected to aisstream.io, saves each new position to positions.csv in DATA_DIR
(a checkout of the `data` branch), and every SYNC_MINUTES commits and pushes any
changes to the `data` branch. pi/install.sh sets this up as a systemd service.

Environment:
  AISSTREAM_API_KEY  required, the aisstream.io API key
  MMSI               vessel to track (default 244000052, the motor yacht Avalon)
  DATA_DIR           checkout of the `data` branch (required)
  SYNC_MINUTES       how often to push to GitHub (default 10)
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import websockets

import collect

STREAM_URL = collect.STREAM_URL
MAX_BACKOFF_SECONDS = 300


def log(message):
    print(f"{collect.iso(datetime.now(timezone.utc))} {message}", flush=True)


def save(row):
    kept = collect.merge(collect.read_rows(), [row])
    if kept:
        collect.append_rows(kept)
        collect.update_status(True, datetime.now(timezone.utc))
    return bool(kept)


async def listen(api_key, mmsi):
    """Stream Avalon's positions forever, reconnecting with backoff when the connection drops."""
    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": [[[-90, -180], [90, 180]]],
        "FiltersShipMMSI": [mmsi],
        "FilterMessageTypes": collect.POSITION_TYPES,
    }
    backoff = 5
    while True:
        try:
            async with websockets.connect(STREAM_URL, open_timeout=30) as ws:
                await ws.send(json.dumps(subscription))
                log(f"Connected to aisstream, listening for MMSI {mmsi}")
                async for raw in ws:
                    msg = json.loads(raw)
                    if "error" in msg:
                        # A bad key won't fix itself; exit so systemd shows the failure.
                        sys.exit(f"aisstream error: {msg['error']}")
                    backoff = 5
                    row = collect.to_row(msg)
                    if row and save(row):
                        log(f"Saved {row['timestamp_utc']} {row['lat']},{row['lon']} sog={row['sog_kn']}")
                log("aisstream closed the connection")
        except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as e:
            log(f"Connection lost ({e!r}); reconnecting in {backoff}s")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


def git(*args):
    return subprocess.run(["git", "-C", str(collect.DATA_DIR), *args], capture_output=True, text=True)


# True at startup so commits left unpushed by a previous run (e.g. no network) go out.
_unpushed = True


def push():
    """Commit whatever changed in DATA_DIR and push it. A failed push is retried next sync."""
    global _unpushed
    git("add", "-A")
    if git("diff", "--cached", "--quiet").returncode != 0:
        git("commit", "-q", "-m", f"Log Avalon positions {collect.iso(datetime.now(timezone.utc))}")
        _unpushed = True
    if not _unpushed:
        return
    result = git("push", "-q", "origin", "HEAD:data")
    if result.returncode == 0:
        _unpushed = False
        log("Pushed new positions to the data branch")
    else:
        log(f"Push failed, will retry: {result.stderr.strip()}")


async def sync_forever(minutes):
    # Also writes the weekly heartbeat so the log shows the tracker is alive.
    while True:
        await asyncio.sleep(minutes * 60)
        collect.update_status(False, datetime.now(timezone.utc))
        await asyncio.to_thread(push)


async def main():
    api_key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if not api_key:
        sys.exit("AISSTREAM_API_KEY is not set (see /etc/avalon-tracker.env on the Pi).")
    if not os.environ.get("DATA_DIR"):
        sys.exit("DATA_DIR is not set; point it at a checkout of the data branch.")
    mmsi = os.environ.get("MMSI", "244000052").strip()
    minutes = float(os.environ.get("SYNC_MINUTES") or "10")
    await asyncio.gather(listen(api_key, mmsi), sync_forever(minutes))


if __name__ == "__main__":
    asyncio.run(main())
