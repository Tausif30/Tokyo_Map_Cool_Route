"""
============================================================================
Tokyo Open Data Hackathon 2026 — Heat Stroke Prevention Project
Nearby_Cool_Spots.py — Pipeline C, script 4

Given a user's (lat, lon), finds and ranks nearby places to cool off:
  - Parks & Green Spaces / Protected Green Spaces  (shade, benches, free,
    no time limit — but you're still outdoors)
  - Drinking Stations   (fast hydration, but no shelter)
  - Convenience Stores  (guaranteed air conditioning + water + a toilet —
    this mirrors Japan's real "みんなのクールシェア" / 涼み処 practice of
    officially pointing people at konbini as heat refuges)
Convenience_Stores.geojson is already sitting in outputs/ per your directory
tree (produced by the OSM_Konbini_Offline.py step your wrangler.py docstring
references) — this script just reads it, it doesn't rebuild it.

RANKING: distance-weighted by a simple, adjustable "shelter value" score per
category (Park=3, Convenience Store=2, Drinking Station=1). This is a
starting heuristic for the demo, not a validated formula — tune the
weights, or replace with something learned from user feedback, once you
have it. If outputs/WBGT_Current_Status.json (written by WBGT_Monitor.py)
shows Severe Warning/Danger, convenience stores are boosted over open parks,
since guaranteed AC matters more than shade alone at that point. This is a
suggestion heuristic, not a guarantee a given store has space/is open to
loitering — say so in the UI.

USAGE (as a library):
    from Nearby_Cool_Spots import nearby_cool_spots
    result = nearby_cool_spots(35.7168, 139.7247, radius_m=800, top_n=5,
                                profile={"age": 70})  # profile is optional

USAGE (CLI demo):
    python Nearby_Cool_Spots.py
    (prints a ranked table for a hardcoded Shinjuku-area point, and writes
    outputs/Nearby_Cool_Spots_Demo.geojson for map preview.)

RUN ORDER: standalone, needs Map_Data.py's outputs (Parks_Green_Spaces,
Protected_Green_Spaces, Drinking_Station) already through Pipeline B
(Map_Data_Fix_Columns.py + Map_Value_Fix.py), plus Convenience_Stores.geojson.
============================================================================
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

try:
    from WBGT_Monitor import classify_for_profile
except ImportError:
    classify_for_profile = None  # profile-aware ranking degrades gracefully — see nearby_cool_spots()

BASE_DIR = Path(__file__).parent
MAP_DIR = BASE_DIR / "outputs"
STATUS_PATH = MAP_DIR / "WBGT_Current_Status.json"

METRIC_CRS = "EPSG:6677"  # Japan Plane Rectangular CS IX (Tokyo)

# ---------------------------------------------------------------------
# TUNABLE RANKING PARAMETERS
# ---------------------------------------------------------------------
SHELTER_VALUE = {
    "Park": 3.0,
    "Convenience Store": 2.0,
    "Drinking Station": 1.0,
}
DISTANCE_PENALTY_PER_KM = 1.5   # score -= this * (distance_km)
HEAT_ALERT_CONVENIENCE_STORE_BOOST = 1.5  # added to Convenience Store's shelter
                                            # value when WBGT is Severe Warning/Danger

LAYER_FILES = {
    "Park": ["Parks_Green_Spaces.geojson", "Protected_Green_Spaces.geojson"],
    "Drinking Station": ["Drinking_Station.geojson"],
    "Convenience Store": ["Convenience_Stores.geojson"],
}


def _load_category(category):
    frames = []
    for filename in LAYER_FILES[category]:
        path = MAP_DIR / filename
        if not path.exists():
            print(f"  WARNING: {filename} not found — skipping")
            continue
        gdf = gpd.read_file(path)
        if gdf.empty:
            continue
        frames.append(gdf)
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    combined = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), crs=frames[0].crs or "EPSG:4326"
    )

    # Drinking stations carry an out_of_service flag (see FIELD_TRANSLATIONS
    # in Map_Data.py) — filter those out defensively. The exact encoding
    # (blank vs a Japanese marker like "○"/"廃止") depends on the source
    # data, so check a sample of real values and tighten this if needed.
    if category == "Drinking Station" and "out_of_service" in combined.columns:
        before = len(combined)
        combined = combined[
            combined["out_of_service"].isna()
            | (combined["out_of_service"].astype(str).str.strip() == "")
        ]
        if len(combined) < before:
            print(f"  filtered out {before - len(combined)} out-of-service drinking station(s)")

    return combined.to_crs(METRIC_CRS)


def _display_name(row, category):
    for col in ("name", "facility_name", "district_en"):
        if col in row and pd.notna(row[col]):
            return str(row[col])
    return category


def _current_wbgt_status():
    if not STATUS_PATH.exists():
        return None
    try:
        with open(STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def nearby_cool_spots(lat, lon, radius_m=800, top_n=5, profile=None):
    """profile: optional dict — see WBGT_Monitor.classify_for_profile() for
    the shape ({'age': int, 'is_pregnant': bool, 'has_chronic_condition':
    bool}). When given, the Convenience Store boost below uses THIS user's
    personalized alert threshold instead of the generic citywide one — e.g.
    a 70-year-old sees the AC-refuge boost kick in a tier earlier than a
    general adult would, for the same WBGT reading."""
    user_point = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(METRIC_CRS).iloc[0]

    status = _current_wbgt_status()
    if status and profile is not None and classify_for_profile is not None:
        heat_alert = classify_for_profile(status["wbgt_c"], profile)["alert"]
    else:
        heat_alert = bool(status and status.get("alert"))
    shelter_value = dict(SHELTER_VALUE)
    if heat_alert:
        shelter_value["Convenience Store"] += HEAT_ALERT_CONVENIENCE_STORE_BOOST

    per_category = {}
    all_candidates = []

    for category in LAYER_FILES:
        gdf = _load_category(category)
        if gdf.empty:
            per_category[category] = []
            continue

        gdf = gdf.copy()
        gdf["distance_m"] = gdf.geometry.distance(user_point)
        nearby = gdf[gdf["distance_m"] <= radius_m].sort_values("distance_m")
        nearby_wgs84 = nearby.to_crs("EPSG:4326")

        entries = []
        for (_, row), (_, row_wgs84) in zip(nearby.iterrows(), nearby_wgs84.iterrows()):
            score = shelter_value[category] - DISTANCE_PENALTY_PER_KM * (row["distance_m"] / 1000)
            centroid = row_wgs84.geometry.centroid
            entry = {
                "category": category,
                "name": _display_name(row, category),
                "distance_m": round(row["distance_m"]),
                "score": round(score, 2),
                "lat": round(centroid.y, 6),
                "lon": round(centroid.x, 6),
            }
            entries.append(entry)
            all_candidates.append(entry)

        per_category[category] = entries[:top_n]

    all_candidates.sort(key=lambda e: e["score"], reverse=True)

    return {
        "query": {"lat": lat, "lon": lon, "radius_m": radius_m},
        "heat_alert_active": heat_alert,
        "wbgt_c": status.get("wbgt_c") if status else None,
        "top_overall": all_candidates[:top_n],
        "by_category": per_category,
    }


def _to_geojson(result):
    features = []
    for entry in result["top_overall"]:
        features.append({
            "type": "Feature",
            "properties": {k: v for k, v in entry.items() if k not in ("lat", "lon")},
            "geometry": {"type": "Point", "coordinates": [entry["lon"], entry["lat"]]},
        })
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    # Demo point — near Shinjuku Station
    lat, lon = 35.7168, 139.7247

    result = nearby_cool_spots(lat, lon, radius_m=800, top_n=5)

    print(f"=== Cool spots near ({lat}, {lon}), radius 800m ===")
    if result["heat_alert_active"]:
        print(f"  HEAT ALERT ACTIVE (WBGT {result['wbgt_c']}\u00b0C) "
              f"— convenience stores boosted in ranking")

    print("\nTop overall:")
    for e in result["top_overall"]:
        print(f"  [{e['score']:>5.2f}] {e['category']:<18s} {e['name']:<30s} {e['distance_m']:>5d} m")

    for category, entries in result["by_category"].items():
        print(f"\n{category}:")
        if not entries:
            print("  (none found within radius, or layer missing)")
        for e in entries:
            print(f"  {e['name']:<30s} {e['distance_m']:>5d} m")

    out_path = MAP_DIR / "Nearby_Cool_Spots_Demo.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(_to_geojson(result), f, ensure_ascii=False)
    print(f"\nWrote {out_path}")