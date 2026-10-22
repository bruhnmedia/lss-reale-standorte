#!/usr/bin/env python3
"""Erzeugung von JSON-Kartenkacheln aus OSM-Standortdaten."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path

TILE_SIZE = 0.25
VALID_CATS = frozenset('fire police hospital drk asb juh mhd dlrg thw berg wasser rescue'.split())


def key(lat: float, lon: float) -> str:
    return f'{math.floor(lat / TILE_SIZE)}_{math.floor(lon / TILE_SIZE)}'


def build(inputs: list[Path], output: Path) -> dict:
    buckets = defaultdict(list)
    ids: set[str] = set()
    for file in inputs:
        with file.open(encoding='utf-8') as stream:
            for row in stream:
                if not row.strip():
                    continue
                item = json.loads(row)
                ident = item.get('id')
                lat = item.get('lat')
                lon = item.get('lon')
                if not isinstance(ident, str) or ident in ids or not isinstance(lat, (float, int)) or not isinstance(lon, (float, int)):
                    continue
                if not -90 <= lat <= 90 or not -180 <= lon <= 180 or item.get('category') not in VALID_CATS:
                    continue
                ids.add(ident)
                buckets[key(lat, lon)].append(item)
    folder = output / 'tiles'
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {'format': 'lss-osm-tiles-v1', 'generatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'tileSizeDegrees': TILE_SIZE, 'source': '© OpenStreetMap-Mitwirkende / Geofabrik (ODbL)',
                'count': len(ids), 'tiles': {}}
    for tile_key, records in sorted(buckets.items()):
        records.sort(key=lambda r: (r['category'], r['name'], r['id']))
        (folder / f'{tile_key}.json').write_text(json.dumps(records, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        manifest['tiles'][tile_key] = len(records)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(ids)} Standorte in {len(buckets)} Kacheln: {output}')
    return manifest


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, action='append', required=True, help='JSONL, wiederholbar')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    build(args.input, args.output)
