"""
============================================================================
Tokyo Open Data Hackathon 2026 — Heat Stroke Prevention Project
Search_Places.py — Pipeline C, script 5

Name-based search across every POI layer OSM_Tokyo_Extract.py (and
Map_Data.py) produced, for the frontend's "type to find a destination"
box. This is a DIFFERENT job from Nearby_Cool_Spots.py's shelter
ranking (parks/konbini/water as heat-refuge candidates only) — here,
"search" means: type part of a name, get back real places across ALL
categories (school, hospital, restaurant, station, ...) ranked by match
quality, each with the lat/lon needed to lock it in as a route
destination or "Point B".

WHY THIS LOADS EVERYTHING INTO MEMORY ONCE, NOT PER REQUEST: with 20+
GeoJSON layers, re-reading them all from disk on every keystroke would
make a debounced search box feel laggy even before any string matching
happens. api.py calls build_index() ONCE at server startup and every
/search-places request reuses that same in-memory list — see the
"USAGE (as a library)" section below for exactly how.

MATCHING, two stages, in this order:
  1. Cheap case-insensitive substring pre-filter over the whole index.
  2. rapidfuzz WRatio scoring, applied to the (usually much smaller)
     stage-1 survivors — or to the whole index if stage 1 came up
     short, so a typo ("Ueno Zool" for "Ueno Zoo") still returns
     something instead of nothing.
Unnamed features (no name/name:en/name:ja/int_name tag at all — quite
common for e.g. City_Offices.geojson entries with no mapped name) are
excluded from the index entirely; there's nothing meaningful to match
against or show the user for those.

USAGE (as a library, this is how api.py should use it):
    from Search_Places import build_index, search_places
    PLACE_INDEX = build_index()          # once, at startup
    results = search_places(PLACE_INDEX, "ueno", limit=10)

USAGE (CLI demo):
    python Search_Places.py "ueno"
============================================================================
"""

import math
import sys
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import geopandas as gpd
from rapidfuzz import fuzz

BASE_DIR = Path(__file__).parent
MAP_DIR = BASE_DIR / "outputs"

# category -> source GeoJSON file(s). Deliberately broader than
# Nearby_Cool_Spots.py's SHELTER_VALUE categories — this is "everything
# a person might search for as a destination", not "everything worth
# recommending as a heat shelter". Missing files are skipped silently
# (see build_index()) so this works fine before every layer exists yet.
SEARCH_CATEGORIES = {
    "Park": ["Parks_Green_Spaces.geojson", "Protected_Green_Spaces.geojson"],
    "Drinking Station": ["Drinking_Station.geojson"],
    "Convenience Store": ["Convenience_Stores.geojson"],
    "Railway Station": ["Railway_Stations.geojson"],
    "Station Entrance": ["Railway_Station_Entrances.geojson"],
    "Kindergarten": ["Kindergartens.geojson"],
    "School": ["Schools.geojson"],
    "Vocational College": ["Vocational_Colleges.geojson"],
    "University": ["Universities.geojson"],
    "Research Institute": ["Research_Institutes.geojson"],
    "Hospital": ["Hospitals.geojson"],
    "Clinic": ["Clinics.geojson"],
    "Restaurant": ["Restaurants.geojson"],
    "Cafe": ["Cafes.geojson"],
    "Fast Food": ["Fast_Food.geojson"],
    "Supermarket": ["Supermarkets.geojson"],
    "Department Store": ["Departmental_Stores.geojson"],
    "Drug Store": ["Drug_Stores.geojson"],
    "Pharmacy": ["Pharmacies.geojson"],
    "Library": ["Libraries.geojson"],
    "City Office": ["City_Offices.geojson"],
    "Office": ["Offices.geojson"],
}

# Preference order when a feature has more than one name tag. name:en
# is prioritized over the raw OSM "name" for tourist-facing search
# (I18n objective) whenever it exists, but "name" is still the far more
# common case in real Tokyo data, so it stays as the primary fallback.
NAME_COLUMNS_PRIORITY = ["name:en", "name", "name:ja", "int_name"]


def _best_name(row):
    for col in NAME_COLUMNS_PRIORITY:
        val = row.get(col) if hasattr(row, "get") else None
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _haversine_m(lat0, lon0, lat1, lon1):
    R = 6_371_000
    dlat, dlon = radians(lat1 - lat0), radians(lon1 - lon0)
    a = sin(dlat / 2) ** 2 + cos(radians(lat0)) * cos(radians(lat1)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def build_index():
    """Load every category's GeoJSON layer(s) once into one flat list of
    {name, category, lat, lon} dicts. Call this once at process startup,
    not per request — see module docstring.

    Real OSM-derived data has edge cases a clean test fixture won't:
    missing/empty geometries, a feature with no centroid, etc. Each row
    is handled defensively — a single bad row gets skipped with a
    printed warning instead of either crashing the whole index build or
    (worse) silently admitting a NaN coordinate that only blows up much
    later, inside an actual search request, in a way that's much harder
    to trace back to its source."""
    records = []
    skipped = 0
    for category, filenames in SEARCH_CATEGORIES.items():
        for filename in filenames:
            path = MAP_DIR / filename
            if not path.exists():
                continue
            gdf = gpd.read_file(path)
            if gdf.empty:
                continue
            if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs("EPSG:4326")
            for _, row in gdf.iterrows():
                name = _best_name(row)
                if not name:
                    continue  # unnamed features aren't searchable by name
                try:
                    geom = row.geometry
                    if geom is None or geom.is_empty:
                        raise ValueError("missing/empty geometry")
                    centroid = geom.centroid
                    lat, lon = centroid.y, centroid.x
                    if math.isnan(lat) or math.isnan(lon):
                        raise ValueError("centroid is NaN")
                except Exception as exc:
                    skipped += 1
                    print(f"  WARNING: skipping {name!r} in {filename} "
                          f"({exc}) — not added to the search index")
                    continue
                records.append({
                    "name": name,
                    "category": category,
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                })
    print(f"Search_Places: indexed {len(records):,} named places "
          f"across {sum(1 for f in SEARCH_CATEGORIES.values())} category file group(s)"
          + (f" ({skipped} row(s) skipped, see warnings above)" if skipped else ""))
    return records


def search_places(index, query, categories=None, limit=20, near=None):
    """index: the list build_index() returned (pass the SAME list every
    call — don't rebuild it per request, see module docstring).
    query: raw text the user typed.
    categories: optional list of category names (values from
      SEARCH_CATEGORIES's keys) to restrict results to.
    limit: max results returned.
    near: optional (lat, lon) tuple. When given, ties among similarly-
      good text matches are broken by distance rather than left in
      whatever order the index happens to be in."""
    query = (query or "").strip().lower()
    if not query:
        return []

    candidates = index if not categories else [
        r for r in index if r["category"] in categories
    ]
    if not candidates:
        return []

    substring_hits = [r for r in candidates if query in r["name"].lower()]
    # If plain substring matching already found plenty, don't bother
    # fuzzy-scoring the whole (possibly much larger) candidate pool.
    pool = substring_hits if len(substring_hits) >= limit else candidates

    scored = [(fuzz.WRatio(query, r["name"].lower()), r) for r in pool]
    scored = [(score, r) for score, r in scored if score > 50]

    if near:
        lat0, lon0 = near
        biased = []
        for score, r in scored:
            distance = _haversine_m(lat0, lon0, r["lat"], r["lon"])
            if math.isnan(distance):
                continue  # shouldn't happen post-build_index() hardening, but never let a NaN reach round()
            biased.append((score, {**r, "distance_m": round(distance)}))
        scored = biased
        # exact/near-exact text matches still win outright; among
        # comparably good matches (within 10 points), nearer wins.
        scored.sort(key=lambda pair: (-round(pair[0] / 10), pair[1]["distance_m"]))
    else:
        scored.sort(key=lambda pair: pair[0], reverse=True)

    return [r for _, r in scored[:limit]]


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "ueno"
    index = build_index()
    print(f"\nResults for {query!r}:")
    for r in search_places(index, query, limit=10):
        print(f"  {r['name']:<30s} [{r['category']}]  ({r['lat']}, {r['lon']})")