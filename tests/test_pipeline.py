import json
import tempfile
import unittest
from pathlib import Path

from tools.build_tiles import build, key
from tools.extract_osm import classify, center


class ExtractorTest(unittest.TestCase):
    def test_classification(self):
        examples = [
            ({'amenity': 'fire_station'}, 'fire'),
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
            tile = key(53.535, 8.664)
            self.assertEqual(result['tiles'][tile], 2)
            self.assertEqual(len(json.loads((root / 'public' / 'tiles' / f'{tile}.json').read_text())), 2)


if __name__ == '__main__':
    unittest.main()
