"""Execute real renderer helpers against mismatched detection/chart windows."""
import subprocess
from pathlib import Path


def test_geometry_uses_candle_time_before_detection_index():
    source = (Path(__file__).resolve().parents[1] / "app/static/pages/structure.js").read_text(
        encoding="utf-8"
    )
    helpers = source[
        source.index("function normalizeTs("):
        source.index("function shouldExtendToLatest(")
    ]
    viewport = source[
        source.index("function visibleGeometryForViewport("):
        source.index("function legendAvailability(")
    ]
    script = helpers + viewport + r"""
const assert = require('node:assert/strict');
for (const days of [7, 1, 1/6]) {
  const start = Date.UTC(2026, 0, 1);
  const candles = Array.from({length: 12}, (_, i) => ({ts_open:start+i*days*86400000}));
  const point = i => ({index:i+180, ts:candles[i].ts_open, price:100+i});
  const item = {system:'swing', points_json:[point(1),point(5),point(9)]};
  const mapped = visibleGeometryForViewport([item],candles,0)[0].points_json;
  assert.deepEqual(mapped.map(p=>p.index),[1,5,9]);
  assert.deepEqual(mapped.map(p=>p.price),[101,105,109]);
  const zoom = visibleGeometryForViewport([item],candles.slice(4),4)[0].points_json;
  assert.deepEqual(zoom.map(p=>p.index),[1,5]);
  const outside = {system:'swing',points_json:[
    {index:999, ts:start-days*86400000, price:50},
    {index:999, ts:start+12*days*86400000, price:500},
    {index:999, price:600},point(5)]};
  assert.deepEqual(visibleGeometryForViewport([outside],candles,0)[0].points_json.map(p=>p.index),[5]);
  assert.equal(localIndexForPoint({index:7},candles,4),3);
}
"""
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
