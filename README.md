# Avalon trip log

Tracks the motor yacht **Avalon** (MMSI 244000052) using free AIS data from [aisstream.io](https://aisstream.io) and draws its route on a map.

## How it works

- A Raspberry Pi stays connected to aisstream.io around the clock, filtered to Avalon's MMSI, and pushes new positions to GitHub every 10 minutes (see [Raspberry Pi](#raspberry-pi)).
- New position reports are appended to `positions.csv` on the [`data` branch](../../tree/data) and committed there, so `main` can keep requiring pull requests. At most one row is kept per 5 minutes.
- [`index.html`](index.html) is a static Leaflet + OpenStreetMap page served by GitHub Pages. It shows the latest position, the route, and stops (stationary within 300 m for over an hour) with arrival and departure times. Gaps of more than 6 hours between reports are drawn dashed.

aisstream only streams live data, so the log starts when the tracker starts. Avalon only appears when it is within range of an AIS receiver that feeds aisstream, so expect gaps at sea.

## Raspberry Pi

On a fresh Raspberry Pi OS (Lite is fine) with internet access:

```sh
curl -fsSL https://raw.githubusercontent.com/theartcher/avalon-trip-log/main/pi/install.sh -o install.sh
sudo bash install.sh
```

The installer asks for your aisstream.io API key (stored only on the Pi, in `/etc/avalon-tracker.env`), installs the `avalon-tracker` service that starts on boot, and prints a deploy key. Add that key under Settings → Deploy keys with **Allow write access** so the Pi can push to the `data` branch. Run the same command again to update the Pi to the latest code.

- Live log: `journalctl -u avalon-tracker -f`
- Change the MMSI or push interval: edit `/etc/avalon-tracker.env`, then `sudo systemctl restart avalon-tracker`

## Map

Turn on GitHub Pages: Settings → Pages → Source "Deploy from a branch" → `main`, folder `/ (root)`.

## GitHub Actions fallback

The **Log Avalon positions** workflow does the same job from GitHub Actions (listening 4 minutes per run, using the `AISSTREAM_API_KEY` Actions secret). GitHub only runs it every few hours, so it hears far less than the Pi. It's disabled while the Pi runs; don't run both, as they push to the same branch.

## Running locally

```sh
pip install -r requirements.txt
AISSTREAM_API_KEY=... LISTEN_SECONDS=60 python scripts/collect.py   # one short listen into ./data
python -m http.server   # then open http://localhost:8000
```
