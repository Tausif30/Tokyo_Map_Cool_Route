"""
Tokyo Open Data Hackathon 2026 — Heat Stroke Prevention Project
Fix mojibake VALUES (not just column names) + add category colors

Pipeline B, stage 3 of 3 — all 3 stages now edit the SAME files in place,
no _merged/_clean/_final suffixes:
  Map_Data.py (creates the 8 files)
    -> Map_Data_Fix_Columns.py (fixes column names in place)
    -> Value_Fix.py (this script, fixes values + adds colors in place)

Follow-up to Map_Data_Fix_Columns.py, which fixes column NAMES in place.
This script fixes the same encoding problem where it also corrupted
VALUES inside features — and now, like Map_Data_Fix_Columns.py, it
overwrites the file directly instead of writing a separate *_final.geojson.
Under the old Points/Lines/Polygons file split we knew exactly which
output files were affected; now that Map_Data.py splits things by theme
instead of geometry type, a given source shapefile's corrupted values
could end up in any of the 8 files depending on what it contains — so this
scans all 8 rather than a hardcoded subset. The detection heuristic only
touches values that actually look garbled, so it's harmless to run on
files that turn out to be clean.

Also adds simplestyle-spec color properties so features render in distinct
colors by category without manual styling — "marker-color" for points,
"stroke" for lines/polygon outlines, "fill" for polygon interiors (these
are DIFFERENT properties per geometry type in the spec; using only
marker-color, like an earlier version of this script did, leaves lines and
polygons uncolored in most viewers). Also adds a plain "color_hex" field
for QGIS/other tools that don't read simplestyle-spec at all.

Also nulls out NoData sentinel values in numeric fields. DBF numeric
columns don't always round-trip a true NULL cleanly, so some of Tokyo's
source shapefiles encode "no data" as a literal magic number instead —
the numeric equivalent of the "-" / "…" placeholders the yearbook CSVs
use for text (see Analysis.py's NA_TOKENS). First spotted in
Street_Trees_Tama.geojson's "tree_count" field (本数): routes with no
recorded tree count come through as a real, plottable "-9999 trees"
instead of empty/missing. -9999 specifically is treated as NoData
anywhere it appears, and additionally ANY negative value is treated as
NoData in fields that can only physically be zero or positive (tree
counts, areas, heights, widths, circumferences) — a shapefile using -1 or
-99 as its "unknown" code would otherwise slip through the exact -9999
check. Like the mojibake fix above, this scans all 8 files rather than
special-casing Street_Trees_Tama, since the same sentinel convention
could show up in any file that shares a source shapefile template.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
FILES = [
    "Water_Canals.geojson",
    "Street_Trees.geojson",
    "Street_Trees_Tama.geojson",
    "Parks_Green_Spaces.geojson",
    "Protected_Green_Spaces.geojson",
    "Drinking_Station.geojson",
    "Public_Facility_Greenery.geojson",
    "Public_Housing_Greenery.geojson",
]

# Distinct, high-contrast color per category (hex) — one entry per category
# Map_Data.py can produce. Street Trees (Tama) shares the same green as
# Street Trees since it's the same underlying thing, just split by
# geometry — give it its own color here if you'd rather tell them apart
# at a glance. Add an entry here if you re-enable another category folder
# in Map_Data.py.
CATEGORY_COLORS = {
    "Water & Canals": "#1976d2",
    "Street Trees": "#8bc34a",
    "Street Trees (Tama)": "#8bc34a",
    "Parks & Green Spaces": "#2e7d32",
    "Protected Green Spaces": "#66bb6a",
    "Drinking Station": "#00bcd4",
    "Public Facility Greenery": "#ff9800",
    "Public Housing Greenery": "#ffb300",
}


def looks_garbled(s):
    """Heuristic: Latin-1-range bytes with no actual Japanese characters
    present is the signature of this specific mojibake pattern."""
    if not isinstance(s, str):
        return False
    has_latin1_supplement = any(0x80 <= ord(c) <= 0xFF for c in s)
    has_real_japanese = any(
        "\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff" for c in s
    )
    return has_latin1_supplement and not has_real_japanese


def recover_value(s):
    if not looks_garbled(s):
        return s
    try:
        return s.encode("latin1").decode("cp932")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s  # couldn't recover — leave as-is rather than corrupt it further


# Exact magic-number NoData codes seen in Tokyo's GIS numeric fields.
# Checked in EVERY field, regardless of name.
NODATA_SENTINEL_VALUES = {-9999, -9999.0}

# Fields that can only ever be zero or positive in real life. Checked
# separately from NODATA_SENTINEL_VALUES so a source file that uses some
# other negative "unknown" code (-1, -99, etc.) still gets caught here
# even though it isn't exactly -9999.
NON_NEGATIVE_FIELDS = {
    "tree_count", "area_m2", "height_m", "canopy_width_m",
    "trunk_circumference_cm",
}


def is_nodata(key, val):
    if isinstance(val, bool):
        return False  # bool is a subclass of int in Python — don't misfire on True/False
    if isinstance(val, (int, float)) and val in NODATA_SENTINEL_VALUES:
        return True
    if key in NON_NEGATIVE_FIELDS and isinstance(val, (int, float)) and val < 0:
        return True
    return False


for filename in FILES:
    path = BASE_DIR / filename
    if not path.exists():
        print(f"Skipping {filename} (not found)")
        continue

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    fixed_count = 0
    nodata_count = 0
    for feat in data["features"]:
        props = feat["properties"]
        for key, val in props.items():
            recovered = recover_value(val)
            if recovered != val:
                props[key] = recovered
                fixed_count += 1
                val = recovered

            if is_nodata(key, val):
                props[key] = None
                nodata_count += 1

        # Color coding for visualization. IMPORTANT: simplestyle-spec (what
        # geojson.io / GitHub / most GeoJSON viewers read) uses DIFFERENT
        # property names depending on geometry type — marker-color is
        # POINTS ONLY. Lines need "stroke", polygons need "stroke" (outline)
        # + "fill" (interior). Setting only marker-color, like this used to,
        # left every LineString/Polygon feature uncolored, so viewers fell
        # back to their own default line color (commonly blue) — that's
        # what the stray "blue lines" following Tama's route-based street
        # trees were.
        color = CATEGORY_COLORS.get(props.get("category"), "#999999")
        props["color_hex"] = color  # plain field, works for any geometry (QGIS etc.)
        geom_type = (feat.get("geometry") or {}).get("type")
        if geom_type in ("Point", "MultiPoint"):
            props["marker-color"] = color
        elif geom_type in ("LineString", "MultiLineString"):
            props["stroke"] = color
            props["stroke-width"] = 2
            props["stroke-opacity"] = 1
        elif geom_type in ("Polygon", "MultiPolygon"):
            props["stroke"] = color
            props["stroke-width"] = 2
            props["stroke-opacity"] = 1
            props["fill"] = color
            props["fill-opacity"] = 0.4

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"{filename}: recovered {fixed_count} garbled values, "
          f"nulled {nodata_count} NoData sentinel values, updated in place")