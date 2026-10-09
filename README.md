# Avalon trip log

Tracks the motor yacht **Avalon** (MMSI 244000052) using free AIS data from [aisstream.io](https://aisstream.io) and draws its route on a map.

## How it works

- Every 30 minutes, the **Log Avalon positions** GitHub Actions workflow listens to aisstream.io for 4 minutes, filtered to Avalon's MMSI.
- New position reports are appended to [`data/positions.csv`](data/positions.csv) and committed, so the repo is the trip log. At most one row is kept per 5 minutes.
- [`index.html`](index.html) is a static Leaflet + OpenStreetMap page served by GitHub Pages. It shows the latest position, the route, and stops (stationary within 300 m for over an hour) with arrival and departure times. Gaps of more than 6 hours between reports are drawn dashed.

aisstream only streams live data, so the log starts from the first run. Avalon only appears when it is within range of an AIS receiver that feeds aisstream, so expect gaps at sea.

## Setup

1. Add your aisstream.io API key as an Actions secret named `AISSTREAM_API_KEY` (Settings → Secrets and variables → Actions).
2. Turn on GitHub Pages: Settings → Pages → Source "Deploy from a branch" → `main`, folder `/ (root)`.
3. Optionally run the workflow once by hand from the Actions tab ("Log Avalon positions" → Run workflow).

GitHub pauses scheduled workflows after 60 days without repo activity. The workflow commits a heartbeat to `data/status.json` at least weekly, so it keeps running even if Avalon goes quiet.

## Backfilling recent history

aisstream has no history, but [VesselAPI](https://vesselapi.com)'s free tier (150 calls a month, no card) keeps about 31 days of positions. To use it, sign up there, add the key as an Actions secret named `VESSELAPI_KEY`, then run **Backfill Avalon history** from the Actions tab with the number of days you want. Each call returns up to 50 positions, and a run stops after `max_calls` calls (20 by default) so it can't use up the month's quota. The positions it finds are merged into `data/positions.csv` in time order.

## Running locally

```sh
pip install -r requirements.txt
AISSTREAM_API_KEY=... LISTEN_SECONDS=60 python scripts/collect.py
python -m http.server   # then open http://localhost:8000
```
