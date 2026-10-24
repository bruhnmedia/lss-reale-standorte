#!/usr/bin/env python3
"""Extraktion von Einsatz- und Hilfsorganisationsstandorten aus OSM."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


def classify(tags: dict[str, str]) -> str | None:
    """Klassifizierung nach OSM-Tags und Trägerangaben."""
    amenity = tags.get('amenity', '').lower()
    emergency = tags.get('emergency', '').lower()
    healthcare = tags.get('healthcare', '').lower()
    service = tags.get('emergency_service', '').lower()
    office = tags.get('office', '').lower()
    combined = ' '.join(tags.get(k, '') for k in ('name', 'operator', 'brand', 'network', 'short_name'))

    def matches(pattern: str) -> bool:
        return bool(re.search(pattern, combined, flags=re.IGNORECASE))

    # Feuerwachen können in OSM auch ausschließlich als Gebäude erfasst sein.
    # Sie dürfen beim Niedersachsen-Export nicht durchs Raster fallen.
    if (amenity == 'fire_station' or emergency == 'fire_station'
            or tags.get('building', '').lower() == 'fire_station'):
        return 'fire'
    if amenity == 'police':
        return 'police'
    if amenity == 'hospital' or healthcare == 'hospital':
        return 'hospital'

    recognized_place = (
        emergency in ('ambulance_station', 'water_rescue', 'water_rescue_station',
                      'mountain_rescue', 'disaster_response', 'rescue_service')
        or amenity in ('rescue_station', 'red_cross', 'mountain_rescue')
        or healthcare == 'ambulance_station'
        or service in ('ambulance', 'technical')
        or (office == 'association' and matches(r'\b(DRK|DLRG|ASB|THW)\b|rotes kreuz|johanniter|malteser|wasserwacht|bergwacht'))
    )
    if not recognized_place:
        return None

    if matches(r'\bDLRG\b|deutsche lebens.rettungs.gesellschaft'):
        return 'dlrg'
    if matches(r'\bTHW\b|technisches hilfswerk'):
        return 'thw'
    if matches(r'\bDRK\b|deutsches rotes kreuz|rotes kreuz|red cross') or amenity == 'red_cross':
        return 'drk'
    if matches(r'\bASB\b|arbeiter.samariter.bund'):
        return 'asb'
    if matches(r'johanniter|\bJUH\b'):
        return 'juh'
    if matches(r'malteser|\bMHD\b'):
        return 'mhd'
    if matches(r'bergwacht') or emergency == 'mountain_rescue' or amenity == 'mountain_rescue':
        return 'berg'
    if matches(r'wasserwacht') or emergency in ('water_rescue', 'water_rescue_station'):
        return 'wasser'
    return 'rescue'


def make_properties(tags: dict[str, str], category: str, obj_id: str) -> dict:
    street = tags.get('addr:street', '').strip()
    number = tags.get('addr:housenumber', '').strip()
    postcode = tags.get('addr:postcode', '').strip()
    city = tags.get('addr:city', '').strip()
    address = ', '.join(s for s in (' '.join(filter(None, (street, number))),
                                     ' '.join(filter(None, (postcode, city)))) if s)
    defaults = {
        'fire': 'Feuerwehr', 'police': 'Polizeidienststelle', 'hospital': 'Krankenhaus',
        'drk': 'DRK-Standort', 'asb': 'ASB-Standort', 'juh': 'Johanniter-Standort',
        'mhd': 'Malteser-Standort', 'dlrg': 'DLRG-Standort', 'thw': 'THW-Standort',
        'berg': 'Bergwacht', 'wasser': 'Wasserwacht', 'rescue': 'Rettungsstandort',
    }
    result = {
        'id': obj_id, 'category': category,
        'name': (tags.get('name') or tags.get('official_name') or defaults[category])[:160],
        'operator': tags.get('operator', '')[:160], 'address': address[:180],
    }
    # Intern für die Dublettenprüfung: Feuerwachen haben Vorrang vor Gebäuden.
    if category == 'fire':
        station = (tags.get('amenity', '').lower() == 'fire_station'
                   or tags.get('emergency', '').lower() == 'fire_station')
        result['_fire_source'] = 'station' if station else 'building'
    return result


def deduplicate_fire_buildings(records: list[dict], max_distance_m: float = 100.0) -> tuple[list[dict], int]:
    """Gebäude an bereits erfassten Feuerwehrstandorten nicht doppelt ausgeben.

    Einzeln erfasste Gebäude bleiben erhalten. Eigenständige explizit
    getaggte Feuerwehrstandorte (amenity/emergency) bleiben immer erhalten.
    Der Abstand ist bewusst klein und gilt nur für Gebäude-Einträge.
    """
    cell_size = 0.002  # ungefähr 220 m Breite in Nord-Süd-Richtung
    stations = [r for r in records if r.get('category') == 'fire']
    # Qualifizierte Feuerwehrstandorte zuerst, dann benannte Gebäude.
    stations.sort(key=lambda r: (
        r.get('_fire_source') != 'station',
        r.get('name', '') == 'Feuerwehr',
        r['id'],
    ))
    spatial: dict[tuple[int, int], list[dict]] = {}
    discarded: set[str] = set()

    def key(r: dict) -> tuple[int, int]:
        return (math.floor(r['lat'] / cell_size), math.floor(r['lon'] / cell_size))

    for item in stations:
        y, x = key(item)
        if item.get('_fire_source') == 'building':
            duplicate = False
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    for existing in spatial.get((y + dy, x + dx), ()):
                        lat_m = (item['lat'] - existing['lat']) * 111195
                        lon_m = ((item['lon'] - existing['lon']) * 111195 *
                                 math.cos(math.radians((item['lat'] + existing['lat']) / 2)))
                        if lat_m * lat_m + lon_m * lon_m <= max_distance_m ** 2:
                            # Bei zwei konkret benannten Gebäuden mit verschiedenen
                            # Namen keine möglicherweise eigenständige Wache verstecken.
                            if (existing.get('_fire_source') == 'building'
                                    and item.get('name') not in ('', 'Feuerwehr')
                                    and existing.get('name') not in ('', 'Feuerwehr')
                                    and item['name'].casefold() != existing['name'].casefold()):
                                continue
                            duplicate = True
                            break
                    if duplicate:
                        break
                if duplicate:
                    break
            if duplicate:
                discarded.add(item['id'])
                continue
        spatial.setdefault((y, x), []).append(item)

    cleaned = []
    for record in records:
        if record['id'] in discarded:
            continue
        obj = record.copy()
        obj.pop('_fire_source', None)
        cleaned.append(obj)
    return cleaned, len(discarded)


def center(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not points:
        return None
    return ((min(a for a, _ in points) + max(a for a, _ in points)) / 2,
            (min(b for _, b in points) + max(b for _, b in points)) / 2)


def extract(path: Path, output: Path) -> int:
    try:
        import osmium
    except ImportError as exc:
        raise SystemExit('Fehlendes Modul: pip install osmium') from exc

    features: dict[str, dict] = {}
    desired_way_nodes: dict[int, list[int]] = {}
    relation_refs: dict[int, list[tuple[str, int]]] = {}
    relation_way_ids: set[int] = set()
    locations_needed: set[int] = set()

    class Scan(osmium.SimpleHandler):
        def node(self, obj):
            if not obj.tags:
                return
            tags = dict(obj.tags)
            cat = classify(tags)
            if cat is not None and obj.location.valid():
                feature = make_properties(tags, cat, f'node/{obj.id}')
                feature['lat'], feature['lon'] = round(obj.location.lat, 7), round(obj.location.lon, 7)
                features[feature['id']] = feature

        def way(self, obj):
            if not obj.tags:
                return
            tags = dict(obj.tags)
            cat = classify(tags)
            if cat is not None:
                refs = [n.ref for n in obj.nodes]
                if refs:
                    desired_way_nodes[obj.id] = refs
                    locations_needed.update(refs)
                    features[f'way/{obj.id}'] = make_properties(tags, cat, f'way/{obj.id}')

        def relation(self, obj):
            if not obj.tags:
                return
            tags = dict(obj.tags)
            cat = classify(tags)
            if cat is None:
                return
            members = [(m.type, m.ref) for m in obj.members if m.type in ('w', 'n')]
            if not members:
                return
            relation_refs[obj.id] = members
            relation_way_ids.update(ref for typ, ref in members if typ == 'w')
            locations_needed.update(ref for typ, ref in members if typ == 'n')
            features[f'relation/{obj.id}'] = make_properties(tags, cat, f'relation/{obj.id}')

    print(f'[1/3] Scan: {path}', flush=True)
    Scan().apply_file(str(path))

    missing_way_ids = relation_way_ids.difference(desired_way_nodes)
    if missing_way_ids:
        class MemberWays(osmium.SimpleHandler):
            def way(self, obj):
                if obj.id in missing_way_ids:
                    refs = [n.ref for n in obj.nodes]
                    desired_way_nodes[obj.id] = refs
                    locations_needed.update(refs)
        print(f'[2/3] {len(missing_way_ids)} Relations-Wege auflösen', flush=True)
        MemberWays().apply_file(str(path))

    locations: dict[int, tuple[float, float]] = {}

    class Nodes(osmium.SimpleHandler):
        def node(self, obj):
            if obj.id in locations_needed and obj.location.valid():
                locations[obj.id] = (obj.location.lat, obj.location.lon)

    print(f'[3/3] {len(locations_needed)} referenzierte Knoten suchen', flush=True)
    if locations_needed:
        Nodes().apply_file(str(path))

    positioned = []
    for obj_id, feat in features.items():
        if obj_id.startswith('way/'):
            way_id = int(obj_id.split('/')[1])
            pt = center([locations[n] for n in desired_way_nodes.get(way_id, ()) if n in locations])
        elif obj_id.startswith('relation/'):
            rel_id = int(obj_id.split('/')[1])
            all_ids: list[int] = []
            for typ, ref in relation_refs.get(rel_id, ()):
                if typ == 'n':
                    all_ids.append(ref)
                elif typ == 'w':
                    all_ids.extend(desired_way_nodes.get(ref, ()))
            pt = center([locations[n] for n in all_ids if n in locations])
        else:
            pt = (feat['lat'], feat['lon'])
        if not pt:
            continue
        feat['lat'] = round(pt[0], 7)
        feat['lon'] = round(pt[1], 7)
        positioned.append(feat)
    unique, duplicate_count = deduplicate_fire_buildings(positioned)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8') as f:
        for feat in unique:
            f.write(json.dumps(feat, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'{len(unique)} Standortobjekte: {output} '
          f'({duplicate_count} überlappende Feuerwehrgebäude ausgeblendet)', flush=True)
    return len(unique)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True, help='Geofabrik *.osm.pbf (auch .osm XML möglich)')
    ap.add_argument('--output', type=Path, required=True, help='Ausgabe *.jsonl')
    args = ap.parse_args()
    extract(args.input, args.output)
