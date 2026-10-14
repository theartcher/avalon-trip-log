"""Temporary: look across Europe for vessels named Avalon (from static/name reports)."""
import asyncio, json, os, time
import websockets

async def main():
    sub = {"APIKey": os.environ["AISSTREAM_API_KEY"], "BoundingBoxes": [[[34, -12], [72, 32]]],
           "FilterMessageTypes": ["ShipStaticData", "StaticDataReport"]}
    named, total, end = {}, 0, time.time() + 420
    while time.time() < end:
        try:
            async with websockets.connect("wss://stream.aisstream.io/v0/stream", max_size=None) as ws:
                await ws.send(json.dumps(sub))
                while time.time() < end:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), end - time.time()))
                    except asyncio.TimeoutError:
                        break
                    if "error" in msg:
                        print("ERROR", msg); return
                    total += 1
                    m = msg.get("MetaData", {})
                    name = (m.get("ShipName") or "").strip().upper()
                    if "AVALON" in name or str(m.get("MMSI")) == "244000052":
                        named.setdefault(m.get("MMSI"), (name, round(m.get("latitude", 0), 3), round(m.get("longitude", 0), 3), m.get("time_utc", "")[:19]))
        except websockets.ConnectionClosed as e:
            print("reconnecting after:", e)
    print("static messages:", total)
    print("vessels named AVALON (or MMSI 244000052):", len(named))
    for k, v in sorted(named.items(), key=lambda kv: str(kv[0])): print("  ", k, v)

asyncio.run(main())
