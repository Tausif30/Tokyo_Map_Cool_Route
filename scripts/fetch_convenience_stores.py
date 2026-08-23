"""Fetch Tokyo convenience stores from OpenStreetMap via Overpass.

The raw Overpass response is cached so normal reruns do not repeatedly hit
the public API. The generated point layer is consumed by
``Nearby_Cool_Spots.py``.

Usage:
    python scripts/fetch_convenience_stores.py
    python scripts/fetch_convenience_stores.py --force
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "outputs" / "Convenience_Stores.geojson"
DEFAULT_CACHE = ROOT_DIR / ".cache" / "osm" / "convenience_stores_tokyo.json"
DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"

# ISO3166-2 JP-13 selects Tokyo Metropolis. ``out center`` supplies a point
# for stores mapped as building ways or relations as well as ordinary nodes.
OVERPASS_QUERY = """
[out:json][timeout:180];
area["ISO3166-2"="JP-13"]["boundary"="administrative"]->.tokyo;
nwr["shop"="convenience"](area.tokyo);
out center tags;
""".strip()


def fetch_overpass(endpoint: str, timeout_s: int) -> dict[str, Any]:
    """Run the convenience-store query and return the decoded response."""
    response = requests.post(
        endpoint,
        data={"data": OVERPASS_QUERY},
        headers={"User-Agent": "TokyoMapCoolRoute/0.1 (hackathon data pipeline)"},
        timeout=timeout_s,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload.get("elements"), list):
        raise ValueError("Overpass response does not contain an elements list")
    return payload


def load_or_fetch(
    cache_path: Path, endpoint: str, timeout_s: int, force: bool
) -> tuple[dict[str, Any], bool]:
    """Return the response and whether it came from the local cache."""
    if cache_path.exists() and not force:
        with cache_path.open(encoding="utf-8") as file:
            return json.load(file), True

    payload = fetch_overpass(endpoint, timeout_s)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False)
    return payload, False


def element_coordinates(element: dict[str, Any]) -> tuple[float, float] | None:
    """Get (longitude, latitude) from an OSM node or an ``out center`` item."""
    if "lon" in element and "lat" in element:
        return float(element["lon"]), float(element["lat"])

    center = element.get("center")
    if isinstance(center, dict) and "lon" in center and "lat" in center:
        return float(center["lon"]), float(center["lat"])
    return None


def to_geojson(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Convert Overpass JSON into a WGS84 point FeatureCollection."""
    retrieved_at = datetime.now(timezone.utc).isoformat()
    features: list[dict[str, Any]] = []
    skipped = 0

    for element in payload.get("elements", []):
        coordinates = element_coordinates(element)
        if coordinates is None:
            skipped += 1
            continue

        tags = element.get("tags") or {}
        osm_type = str(element.get("type", ""))
        osm_id = element.get("id")
        name = (
            tags.get("name")
            or tags.get("name:en")
            or tags.get("brand")
            or tags.get("brand:en")
            or "Convenience Store"
        )

        properties = {
            "name": name,
            "name_en": tags.get("name:en"),
            "brand": tags.get("brand"),
            "operator": tags.get("operator"),
            "opening_hours": tags.get("opening_hours"),
            "wheelchair": tags.get("wheelchair"),
            "category": "Convenience Store",
            "subcategory": "OpenStreetMap shop=convenience",
            "osm_type": osm_type,
            "osm_id": osm_id,
            "osm_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
            "source_dataset": "OpenStreetMap via Overpass API",
        }
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {"type": "Point", "coordinates": coordinates},
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "Tokyo Convenience Stores",
        "attribution": "© OpenStreetMap contributors",
        "license": "Open Database License (ODbL)",
        "retrieved_at": retrieved_at,
        "query": OVERPASS_QUERY,
        "features": features,
    }
    return geojson, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build outputs/Convenience_Stores.geojson from OpenStreetMap"
    )
    parser.add_argument("--force", action="store_true", help="ignore and replace the cache")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Overpass interpreter URL")
    parser.add_argument("--timeout", type=int, default=240, help="HTTP timeout in seconds")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload, from_cache = load_or_fetch(
        args.cache, args.endpoint, args.timeout, args.force
    )
    geojson, skipped = to_geojson(payload)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(geojson, file, ensure_ascii=False)

    origin = f"cache {args.cache}" if from_cache else args.endpoint
    print(f"Loaded {len(payload['elements']):,} OSM element(s) from {origin}")
    print(f"Wrote {len(geojson['features']):,} convenience-store point(s) to {args.output}")
    if skipped:
        print(f"Skipped {skipped:,} element(s) without coordinates")


if __name__ == "__main__":
    main()
