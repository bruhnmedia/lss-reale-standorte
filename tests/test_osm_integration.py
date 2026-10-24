"""Integrationstest: Feuerwehrpunkte und Gebäude in Niedersachsen (OSM-XML)."""
import json
import tempfile
import unittest
from pathlib import Path

from tools.build_tiles import build, key
from tools.extract_osm import extract


SAMPLE_OSM = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="BRUHN MEDIA | OSM Tests">
  <node id="1" lat="53.73923" lon="8.91587">
    <tag k="amenity" v="fire_station"/>
    <tag k="name" v="Freiwillige Feuerwehr Ihlienworth"/>
  </node>
  <node id="2" lat="53.77000" lon="8.93000">
    <tag k="emergency" v="fire_station"/>
    <tag k="name" v="Feuerwehr Test NDS"/>
  </node>
  <node id="3" lat="53.73000" lon="8.92000">
    <tag k="shop" v="supermarket"/>
    <tag k="name" v="Feuerwehr Fanartikel"/>
  </node>
  <node id="10" lat="53.73920" lon="8.91580"/>
  <node id="11" lat="53.73930" lon="8.91580"/>
  <node id="12" lat="53.73930" lon="8.91600"/>
  <node id="13" lat="53.73920" lon="8.91600"/>
  <node id="20" lat="53.81000" lon="8.90000"/>
  <node id="21" lat="53.81010" lon="8.90000"/>
  <node id="22" lat="53.81010" lon="8.90020"/>
  <node id="23" lat="53.81000" lon="8.90020"/>
  <way id="500">
    <nd ref="10"/><nd ref="11"/><nd ref="12"/><nd ref="13"/><nd ref="10"/>
    <tag k="building" v="fire_station"/>
  </way>
  <way id="501">
    <nd ref="20"/><nd ref="21"/><nd ref="22"/><nd ref="23"/><nd ref="20"/>
    <tag k="building" v="fire_station"/>
    <tag k="name" v="Feuerwehrhaus Test NDS"/>
  </way>
</osm>
"""


class OsmFireStationIntegration(unittest.TestCase):
    def test_extract_realistic_niedersachsen_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            osm = root / "niedersachsen-sample.osm"
            result = root / "standorte.jsonl"
            osm.write_text(SAMPLE_OSM, encoding="utf-8")

            self.assertEqual(extract(osm, result), 3)
            data = [json.loads(line) for line in result.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({x["id"] for x in data}, {"node/1", "node/2", "way/501"})
            self.assertTrue(all(x["category"] == "fire" for x in data))
            self.assertTrue(all("_fire_source" not in x for x in data))
            self.assertTrue(all(51.0 <= x["lat"] <= 55.0 and 6.0 <= x["lon"] <= 12.0 for x in data))

            tiles = root / "tiles-output"
            manifest = build([result], tiles)
            self.assertEqual(manifest["count"], 3)
            nearby_key = key(53.73923, 8.91587)
            near_tile = json.loads((tiles / "tiles" / f"{nearby_key}.json").read_text(encoding="utf-8"))
            self.assertEqual(sum(x["id"] == "node/1" for x in near_tile), 1)


if __name__ == "__main__":
    unittest.main()
