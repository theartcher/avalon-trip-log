"""Temporary: check aisstream sends data for the Netherlands and whether Avalon is in it."""
import asyncio, json, os, time
from collections import Counter
import websockets

async def main():
    sub = {"APIKey": os.environ["AISSTREAM_API_KEY"],
           "BoundingBoxes": [[[50.7, 2.5], [54.0, 7.3]]]}  # Netherlands + coast
    types, mmsis, avalon = Counter(), set(), []
    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
        await ws.send(json.dumps(sub))
        end = time.time() + 180
        while time.time() < end:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), end - time.time()))
            except asyncio.TimeoutError:
                break
            if "error" in msg:
                print("ERROR", msg); return
            types[msg.get("MessageType")] += 1
            m = msg.get("MetaData", {})
            mmsis.add(m.get("MMSI"))
            if str(m.get("MMSI")) == "244000052":
                avalon.append((msg.get("MessageType"), m.get("ShipName"), m.get("latitude"), m.get("longitude"), m.get("time_utc")))
    print("total messages:", sum(types.values()))
    print("distinct vessels:", len(mmsis))
    print("by type:", dict(types.most_common()))
    print("avalon messages:", len(avalon))
    for a in avalon[:20]: print("  ", a)
    names = [m for m in mmsis if str(m).startswith("244")]
    print("dutch (244*) vessels heard:", len(names))

asyncio.run(main())
