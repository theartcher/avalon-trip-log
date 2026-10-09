"""Listen to aisstream.io for a few minutes and append new Avalon positions to data/positions.csv.

Usage: AISSTREAM_API_KEY=... python scripts/collect.py

Environment:
  AISSTREAM_API_KEY  required, the aisstream.io API key
  MMSI               vessel to track (default 244000052, the motor yacht Avalon)
  LISTEN_SECONDS     how long to listen per run (default 240)
"""

import asyncio
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import websockets

STREAM_URL = "wss://stream.aisstream.io/v0/stream"
ROOT = Path(__file__).resolve().parent.parent
POSITIONS_CSV = ROOT / "data" / "positions.csv"
STATUS_JSON = ROOT / "data" / "status.json"

FIELDS = ["timestamp_utc", "lat", "lon", "sog_kn", "cog", "heading", "nav_status", "message_type", "ship_name"]
POSITION_TYPES = ["PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport"]

# Keep at most one row per this interval, so a moored yacht reporting every few minutes
# doesn't flood the log. Stops are still detectable because each run adds a row.
MIN_ROW_INTERVAL = timedelta(minutes=5)
# Refresh status.json at least this often even without new positions, so the repo keeps
# getting commits and GitHub doesn't pause the scheduled workflow after 60 idle days.
HEARTBEAT_INTERVAL = timedelta(days=7)

_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?:\.(\d+))?")


def parse_time(value):
    """aisstream sends e.g. '2024-05-01 12:34:56.123456789 +0000 UTC'."""
    m = _TIME_RE.match(value or "")
    if not m:
        return datetime.now(timezone.utc).replace(microsecond=0)
    date, clock, _fraction = m.groups()
    return datetime.fromisoformat(f"{date}T{clock}+00:00")


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_row(msg):
    """Turn one aisstream message into a CSV row dict, or None if it isn't a usable position."""
    msg_type = msg.get("MessageType")
    if msg_type not in POSITION_TYPES:
        return None
    meta = msg.get("MetaData") or {}
    body = (msg.get("Message") or {}).get(msg_type) or {}
    lat = body.get("Latitude", meta.get("latitude"))
    lon = body.get("Longitude", meta.get("longitude"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None  # AIS uses 91/181 for "not available"
    sog = body.get("Sog")
    cog = body.get("Cog")
    heading = body.get("TrueHeading")
    return {
        "timestamp_utc": iso(parse_time(meta.get("time_utc"))),
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "sog_kn": "" if sog is None or sog >= 102.3 else f"{sog:.1f}",
        "cog": "" if cog is None or cog >= 360 else f"{cog:.1f}",
        "heading": "" if heading is None or heading == 511 else str(heading),
        "nav_status": str(body.get("NavigationalStatus", "")),
        "message_type": msg_type,
        "ship_name": (meta.get("ShipName") or "").replace(",", " ").strip(),
    }


async def listen(api_key, mmsi, seconds):
    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": [[[-90, -180], [90, 180]]],
        "FiltersShipMMSI": [mmsi],
        "FilterMessageTypes": POSITION_TYPES,
    }
    rows = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    async with websockets.connect(STREAM_URL, open_timeout=30) as ws:
        await ws.send(json.dumps(subscription))
        while (remaining := deadline - loop.time()) > 0:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            except websockets.ConnectionClosed as e:
                print(f"aisstream closed the connection: {e}")
                break
            msg = json.loads(raw)
            if "error" in msg:
                raise RuntimeError(f"aisstream error: {msg['error']}")
            row = to_row(msg)
            if row:
                print(f"  {row['timestamp_utc']} {row['lat']},{row['lon']} sog={row['sog_kn']}")
                rows.append(row)
    return rows


def read_rows():
    if not POSITIONS_CSV.exists():
        return []
    with POSITIONS_CSV.open(newline="") as f:
        return list(csv.DictReader(f))


def merge(existing, new_rows):
    """Return the rows from new_rows worth appending, oldest first."""
    last = parse_iso(existing[-1]["timestamp_utc"]) if existing else None
    kept = []
    for row in sorted(new_rows, key=lambda r: r["timestamp_utc"]):
        t = parse_iso(row["timestamp_utc"])
        if last is None or t - last >= MIN_ROW_INTERVAL:
            kept.append(row)
            last = t
    return kept


def parse_iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def append_rows(rows):
    POSITIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    new_file = not POSITIONS_CSV.exists()
    with POSITIONS_CSV.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def rewrite_merged(new_rows):
    """Merge new_rows into the whole log in time order, thinning to one row per MIN_ROW_INTERVAL.

    Used for backfills, whose rows can be older than what is already logged.
    Returns how many rows the log grew by.
    """
    existing = read_rows()
    merged = []
    for row in sorted(existing + new_rows, key=lambda r: r["timestamp_utc"]):
        if merged and parse_iso(row["timestamp_utc"]) - parse_iso(merged[-1]["timestamp_utc"]) < MIN_ROW_INTERVAL:
            continue
        merged.append({k: row.get(k, "") for k in FIELDS})
    POSITIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with POSITIONS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(merged)
    return len(merged) - len(existing)


def update_status(added, now):
    status = json.loads(STATUS_JSON.read_text()) if STATUS_JSON.exists() else {}
    last_heartbeat = status.get("last_heartbeat_utc")
    stale = last_heartbeat is None or now - parse_iso(last_heartbeat) >= HEARTBEAT_INTERVAL
    if not added and not stale:
        return
    status["last_heartbeat_utc"] = iso(now)
    if added:
        status["last_new_position_utc"] = iso(now)
    STATUS_JSON.write_text(json.dumps(status, indent=2) + "\n")


def main():
    api_key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if not api_key:
        sys.exit("AISSTREAM_API_KEY is not set. Add it under Settings > Secrets and variables > Actions.")
    mmsi = os.environ.get("MMSI", "244000052").strip()
    seconds = int(os.environ.get("LISTEN_SECONDS", "240"))

    print(f"Listening to aisstream for MMSI {mmsi} for {seconds}s...")
    received = asyncio.run(listen(api_key, mmsi, seconds))
    kept = merge(read_rows(), received)
    if kept:
        append_rows(kept)
    update_status(bool(kept), datetime.now(timezone.utc))
    print(f"Received {len(received)} position reports, appended {len(kept)} rows.")


if __name__ == "__main__":
    main()
