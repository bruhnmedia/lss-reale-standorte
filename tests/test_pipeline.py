import json
import tempfile
import unittest
from pathlib import Path

from tools.build_tiles import build, key
from tools.extract_osm import classify, center, deduplicate_fire_buildings, make_properties


class ExtractorTest(unittest.TestCase):
    def test_classification(self):
        examples = [
            ({'amenity': 'fire_station'}, 'fire'),
            ({'building': 'fire_station', 'name': 'Freiwillige Feuerwehr'}, 'fire'),
            ({'emergency': 'fire_station'}, 'fire'),
            ({'building': 'yes', 'name': 'Feuerwehr Fanartikel'}, None),
            ({'amenity': 'police'}, 'police'),
            ({'healthcare': 'hospital'}, 'hospital'),
            ({'emergency': 'ambulance_station', 'operator': 'DRK Kreisverband'}, 'drk'),
            ({'emergency': 'disaster_response', 'operator': 'Technisches Hilfswerk'}, 'thw'),
            ({'emergency': 'water_rescue', 'name': 'DLRG Wache'}, 'dlrg'),
            ({'emergency': 'mountain_rescue'}, 'berg'),
            ({'office': 'association', 'name': 'Malteser Hilfsdienst'}, 'mhd'),
            ({'shop': 'supermarket', 'name': 'Feuerwehr Fanartikel'}, None),
        ]
        for tags, expected in examples:
            with self.subTest(tags=tags):
                self.assertEqual(classify(tags), expected)


    def test_fire_source_tagging(self):
        official = make_properties({'amenity': 'fire_station', 'name': 'FF Ihlienworth'}, 'fire', 'node/1')
        building = make_properties({'building': 'fire_station'}, 'fire', 'way/2')
        self.assertEqual(official['_fire_source'], 'station')
        self.assertEqual(building['_fire_source'], 'building')

    def test_fire_station_and_building_not_double_counted(self):
        # Ihlienworth, Niedersachsen: Stationspunkt und Gebäude liegen nebeneinander.
        official = {'id': 'node/1', 'category': 'fire', 'name': 'Freiwillige Feuerwehr Ihlienworth',
                    '_fire_source': 'station', 'lat': 53.73923, 'lon': 8.91587}
        building = {'id': 'way/2', 'category': 'fire', 'name': 'Feuerwehr',
                    '_fire_source': 'building', 'lat': 53.73937, 'lon': 8.91592}
        other = {'id': 'way/3', 'category': 'fire', 'name': 'Freiwillige Feuerwehr Neuhaus',
                 '_fire_source': 'building', 'lat': 53.81, 'lon': 8.90}
        records, duplicates = deduplicate_fire_buildings([building, other, official])
        self.assertEqual(duplicates, 1)
        self.assertEqual({r['id'] for r in records}, {'node/1', 'way/3'})
        self.assertTrue(all('_fire_source' not in r for r in records))

    def test_building_only_and_distinct_fire_stations(self):
        base = {'category': 'fire', '_fire_source': 'building', 'lat': 53.739,
                'lon': 8.915}
        nearby = [{**base, 'id': 'way/5', 'name': 'Feuerwehr', 'lat': 53.73910},
                  {**base, 'id': 'way/6', 'name': 'Feuerwehr', 'lat': 53.73913},
                  {**base, 'id': 'way/7', 'name': 'FF A', 'lat': 53.7404}]
        records, duplicates = deduplicate_fire_buildings(nearby)
        self.assertEqual(duplicates, 1)
        self.assertEqual(len(records), 2)

        # Zwei getrennt benannte Feuerwehreinheiten nicht zusammenwerfen.
        nearby[0]['name'] = 'FF Abteilung A'
        nearby[1]['name'] = 'FF Abteilung B'
        records, duplicates = deduplicate_fire_buildings(nearby)
        self.assertEqual(duplicates, 0)
        self.assertEqual(len(records), 3)

    def test_explicit_fire_stations_never_collapsed(self):
        official = {'category': 'fire', '_fire_source': 'station',
                    'lat': 53.73923, 'lon': 8.91587}
        records, duplicates = deduplicate_fire_buildings([
            {**official, 'id': 'node/1', 'name': 'FF A'},
            {**official, 'id': 'way/2', 'name': 'FF B'}])
        self.assertEqual(duplicates, 0)
        self.assertEqual(len(records), 2)

    def test_center(self):
        self.assertEqual(center([(1., 2.), (3., 4.)]), (2., 3.))
        self.assertIsNone(center([]))

    def test_tiles_and_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [
                {'id':'node/123','lat':53.535,'lon':8.664,'name':'Feuerwehr Test','category':'fire'},
                {'id':'node/123','lat':53.535,'lon':8.664,'name':'Feuerwehr Test','category':'fire'},
                {'id':'way/456','lat':53.535,'lon':8.664,'name':'Krankenhaus Test','category':'hospital'},
            ]
            source = root / 'sample.jsonl'
            source.write_text(''.join(json.dumps(x) + '\n' for x in records), encoding='utf-8')
            result = build([source], root / 'public')
            self.assertEqual(result['count'], 2)
            self.assertEqual(result['countsByCategory'], {'fire': 1, 'hospital': 1})
            tile = key(53.535, 8.664)
            self.assertEqual(result['tiles'][tile], 2)
            self.assertEqual(len(json.loads((root / 'public' / 'tiles' / f'{tile}.json').read_text())), 2)


if __name__ == '__main__':
    unittest.main()
