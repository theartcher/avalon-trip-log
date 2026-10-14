"""Temporary: look worldwide for vessels named Avalon and for MMSI 244000052."""
import asyncio, json, os, time
import websockets

async def main():
    sub = {"APIKey": os.environ["AISSTREAM_API_KEY"], "BoundingBoxes": [[[-90, -180], [90, 180]]]}
    named, target, total = {}, [], 0
    async with websockets.connect("wss://stream.aisstream.io/v0/stream", max_size=None) as ws:
        await ws.send(json.dumps(sub))
        end = time.time() + 420
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
            if "AVALON" in name:
                named.setdefault(m.get("MMSI"), (name, msg.get("MessageType"), round(m.get("latitude", 0), 3), round(m.get("longitude", 0), 3), m.get("time_utc", "")[:19]))
            if str(m.get("MMSI")) == "244000052":
                target.append((msg.get("MessageType"), name, m.get("latitude"), m.get("longitude")))
    print("total messages:", total)
    print("MMSI 244000052 messages:", len(target), target[:5])
    print("vessels with AVALON in the name:", len(named))
    for k, v in sorted(named.items(), key=lambda kv: str(kv[0])): print("  ", k, v)

asyncio.run(main())
