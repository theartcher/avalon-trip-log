// Pure helpers for turning positions.csv into a route, stops and stats.
// Works in the browser (window.Track) and in Node (module.exports) for testing.
(function (root) {
  const STOP_RADIUS_KM = 0.3;          // points within this distance count as "not moving"
  const STOP_MIN_MINUTES = 60;         // stationary at least this long counts as a stop
  const GAP_HOURS = 6;                 // no reports this long: draw the leg as a dashed gap
  const MAX_PLAUSIBLE_KN = 60;         // ignore jumps faster than this when summing distance

  function parseCsv(text) {
    const lines = text.trim().split(/\r?\n/);
    if (lines.length < 2) return [];
    const header = lines[0].split(",");
    return lines.slice(1).map((line) => {
      const cells = line.split(",");
      const row = {};
      header.forEach((h, i) => (row[h] = cells[i] ?? ""));
      return {
        time: new Date(row.timestamp_utc),
        lat: Number(row.lat),
        lon: Number(row.lon),
        sog: row.sog_kn === "" ? null : Number(row.sog_kn),
        cog: row.cog === "" ? null : Number(row.cog),
        heading: row.heading === "" ? null : Number(row.heading),
        name: row.ship_name,
      };
    }).filter((p) => !isNaN(p.time) && isFinite(p.lat) && isFinite(p.lon))
      .sort((a, b) => a.time - b.time);
  }

  function distanceKm(a, b) {
    const rad = Math.PI / 180;
    const dLat = (b.lat - a.lat) * rad;
    const dLon = (b.lon - a.lon) * rad;
    const h = Math.sin(dLat / 2) ** 2 +
      Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  }

  // Groups consecutive points that stay within STOP_RADIUS_KM of the group's first point.
  // A group lasting STOP_MIN_MINUTES or more is a stop; the last one may still be ongoing.
  function findStops(points) {
    const stops = [];
    let start = 0;
    const close = (end) => {
      const group = points.slice(start, end);
      const minutes = (group[group.length - 1].time - group[0].time) / 60000;
      if (minutes >= STOP_MIN_MINUTES) {
        stops.push({
          lat: group.reduce((s, p) => s + p.lat, 0) / group.length,
          lon: group.reduce((s, p) => s + p.lon, 0) / group.length,
          arrived: group[0].time,
          departed: group[group.length - 1].time,
          minutes,
          ongoing: end === points.length,
        });
      }
    };
    for (let i = 1; i < points.length; i++) {
      if (distanceKm(points[start], points[i]) > STOP_RADIUS_KM) {
        close(i);
        start = i;
      }
    }
    if (points.length) close(points.length);
    return stops;
  }

  // Splits the route into legs. Consecutive reports more than GAP_HOURS apart get a "gap" leg.
  function legs(points) {
    const out = [];
    let current = [];
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      if (current.length && (p.time - points[i - 1].time) / 3.6e6 > GAP_HOURS) {
        out.push({ gap: false, points: current });
        out.push({ gap: true, points: [points[i - 1], p] });
        current = [];
      }
      current.push(p);
    }
    if (current.length) out.push({ gap: false, points: current });
    return out.filter((l) => l.points.length > 1);
  }

  function distanceNm(points) {
    let km = 0;
    for (let i = 1; i < points.length; i++) {
      const d = distanceKm(points[i - 1], points[i]);
      const hours = (points[i].time - points[i - 1].time) / 3.6e6;
      if (hours > 0 && d / 1.852 / hours > MAX_PLAUSIBLE_KN) continue;
      km += d;
    }
    return km / 1.852;
  }

  const api = { parseCsv, distanceKm, findStops, legs, distanceNm };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Track = api;
})(this);
