"""Temporary: speed and position of the three vessels named Avalon."""
import asyncio, json, os, time
import websockets

IDS = ["211705110", "244330648", "244850110"]
async def main():
    sub = {"APIKey": os.environ["AISSTREAM_API_KEY"], "BoundingBoxes": [[[-90, -180], [90, 180]]],
           "FiltersShipMMSI": IDS}
    seen, end = {}, time.time() + 300
    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
        await ws.send(json.dumps(sub))
        while time.time() < end:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), end - time.time()))
            except asyncio.TimeoutError:
                break
            t = msg.get("MessageType"); m = msg.get("MetaData", {}); b = msg.get("Message", {}).get(t, {})
            if "Sog" in b:
                seen.setdefault(m.get("MMSI"), []).append((m.get("time_utc", "")[11:19], round(b.get("Latitude"), 4), round(b.get("Longitude"), 4), b.get("Sog"), b.get("Cog")))
            elif t == "ShipStaticData":
                d = b.get("Dimension", {}); print("static", m.get("MMSI"), b.get("Name"), "type", b.get("Type"), "len", d.get("A", 0) + d.get("B", 0), "dest", b.get("Destination"))
    for k, v in seen.items():
        print(k, len(v), "reports; first", v[0], "last", v[-1])

asyncio.run(main())
