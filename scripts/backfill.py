"""Backfill recent Avalon positions from VesselAPI's free tier into data/positions.csv.

aisstream.io is live-only; VesselAPI keeps about 31 days of positions and its free
tier allows 150 calls a month, each returning up to 50 positions.

Usage: VESSELAPI_KEY=... DAYS=1 python scripts/backfill.py

Environment:
  VESSELAPI_KEY  required, the vesselapi.com API key
  MMSI           vessel to backfill (default 244000052, the motor yacht Avalon)
  DAYS           how many days back to fetch, 1-31 (default 1)
  MAX_CALLS      stop after this many API calls (default 20, of 150 free per month)
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import collect

API_URL = "https://api.vesselapi.com/v1/vessels/positions"
PAGE_SIZE = 50


def fetch_page(api_key, params):
    req = urllib.request.Request(
        f"{API_URL}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        sys.exit(f"VesselAPI returned HTTP {e.code}: {body}")


def to_row(p):
    """Turn one VesselAPI position into a CSV row dict, or None if unusable."""
    lat, lon = p.get("latitude"), p.get("longitude")
    if p.get("suspected_glitch") or lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    try:
        # Drop fractional seconds; some APIs send nanoseconds, which fromisoformat rejects.
        t = collect.parse_iso(re.sub(r"\.\d+", "", p["timestamp"]))
    except (KeyError, ValueError):
        return None
    sog, cog, heading = p.get("sog"), p.get("cog"), p.get("heading")
    return {
        "timestamp_utc": collect.iso(t),
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "sog_kn": "" if sog is None or sog >= 102.3 else f"{sog:.1f}",
        "cog": "" if cog is None or cog >= 360 else f"{cog:.1f}",
        "heading": "" if heading is None or heading == 511 else str(heading),
        "nav_status": "" if p.get("nav_status") is None else str(p["nav_status"]),
        "message_type": "VesselAPI",
        "ship_name": (p.get("vessel_name") or "").replace(",", " ").strip(),
    }


def main():
    api_key = os.environ.get("VESSELAPI_KEY", "").strip()
    if not api_key:
        sys.exit("VESSELAPI_KEY is not set. Add it under Settings > Secrets and variables > Actions.")
    mmsi = os.environ.get("MMSI", "244000052").strip()
    days = max(1, min(31, int(os.environ.get("DAYS") or "1")))
    max_calls = int(os.environ.get("MAX_CALLS") or "20")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    params = {
        "filter.ids": mmsi,
        "filter.idType": "mmsi",
        "time.from": collect.iso(now - timedelta(days=days)),
        "time.to": collect.iso(now),
        "pagination.limit": PAGE_SIZE,
    }
    print(f"Fetching {days} day(s) of positions for MMSI {mmsi} from VesselAPI...")
    rows, calls = [], 0
    while calls < max_calls:
        page = fetch_page(api_key, params)
        calls += 1
        rows += [r for r in map(to_row, page.get("vesselPositions") or []) if r]
        token = page.get("nextToken")
        if not token:
            break
        params["pagination.nextToken"] = token
    else:
        print(f"Stopped after MAX_CALLS={max_calls}; older or newer positions may remain.")

    added = collect.rewrite_merged(rows)
    print(f"Used {calls} API call(s), received {len(rows)} positions, log grew by {added} rows.")


if __name__ == "__main__":
    main()
