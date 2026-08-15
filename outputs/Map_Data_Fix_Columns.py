"""
Fix mojibake attribute names in the map GeoJSON files produced by
Map_Data.py (Water_Canals, Street_Trees, Street_Trees_Tama,
Parks_Green_Spaces, Protected_Green_Spaces, Drinking_Station,
Public_Facility_Greenery, Public_Housing_Greenery).

Pipeline B, stage 2 of 3 — all 3 stages now edit the SAME files in place,
no _merged/_clean/_final suffixes:
  Map_Data.py (creates the 8 files)
    -> Map_Data_Fix_Columns.py (this script, fixes column names in place)
    -> Value_Fix.py (fixes values + adds colors in place)

If you ever want a before/after copy for comparison, just duplicate a file
yourself before running this.

ROOT CAUSE: many of Tokyo's GIS shapefiles don't ship a .cpg file
declaring their encoding, so GDAL/Fiona defaulted to Latin-1 when reading
DBF field names that were actually Shift-JIS (cp932). Some shapefiles DID
have a proper encoding declared and came through fine — which is why a
file can end up with both a correct column ("区市町村") and a garbled
twin of the exact same field ("\x8bæ\x8es\x92¬\x91º") from a different
source file.

This script:
  1. Detects garbled column names and recovers the original Japanese via
     the latin1 -> cp932 round-trip
  2. Translates every Japanese column name (garbled or not) to English
  3. Merges duplicate columns that turned out to be the same field
  4. Overwrites the file in place with the fixed, fully-English version

Works on files of any size (streams through features, doesn't build the
whole English-language dictionary into memory more than once).
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

# Japanese field name -> English. Add to this if you spot an untranslated
# column in the script's printed warnings.
FIELD_TRANSLATIONS = {
    "地点コード": "point_code", "名称": "name", "区市町村": "municipality",
    "所在地": "address", "流入河川": "inflow_river", "面積m2": "area_m2",
    "制度種別": "program_type", "設置年月日": "established_date",
    "設置主体": "established_by", "管理主体": "managed_by",
    "指定根拠": "designation_basis", "備考": "notes", "樹種": "species",
    "区分": "classification", "樹高m": "height_m", "枝張ｍ": "canopy_width_m",
    "幹周cm": "trunk_circumference_cm", "道路種別": "road_type",
    "整理番号": "serial_number", "路線名": "route_name",
    "通称道路名": "common_road_name", "道路通称名": "common_road_name",
    "所管": "jurisdiction", "種別": "type", "指定年月日": "designation_date",
    "位置": "location", "開園年月日": "opening_date",
    "設置等根拠": "establishment_basis", "本数": "tree_count",
}

# Columns we already know are clean English from our own earlier script
KEEP_AS_IS = {"category", "subcategory", "source_file", "source_dataset", "geometry"}


def recover_column_name(col):
    """Fix mojibake (latin1-decoded Shift-JIS) column names where possible."""
    if col in KEEP_AS_IS or col in FIELD_TRANSLATIONS:
        return col
    try:
        recovered = col.encode("latin1").decode("cp932")
        return recovered
    except (UnicodeEncodeError, UnicodeDecodeError):
        return col  # wasn't mojibake — leave as-is


def translate_column(col):
    return FIELD_TRANSLATIONS.get(col, col)


def fix_file(filename):
    path = BASE_DIR / filename
    if not path.exists():
        print(f"Skipping {filename} (not found next to this script)")
        return

    print(f"\nProcessing {filename} ...")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # Build the rename map from whatever columns actually appear in the file
    all_cols = set()
    for feat in data["features"]:
        all_cols.update(feat["properties"].keys())

    rename_map = {}
    unmatched = []
    for col in all_cols:
        recovered = recover_column_name(col)
        english = translate_column(recovered)
        rename_map[col] = english
        if english == recovered and english not in KEEP_AS_IS and any(
            ord(ch) > 127 for ch in english
        ):
            unmatched.append((col, recovered))

    if unmatched:
        print("  NOTE: these columns aren't in the translation dictionary yet "
              "— add them to FIELD_TRANSLATIONS if they matter:")
        for orig, recovered in unmatched:
            print(f"    {orig!r} (recovered: {recovered!r})")

    # Apply renames, merging duplicate columns (e.g. a garbled and a clean
    # version of the same field) by taking whichever value is non-null
    for feat in data["features"]:
        new_props = {}
        for old_key, value in feat["properties"].items():
            new_key = rename_map[old_key]
            if new_key in new_props and new_props[new_key] is not None:
                continue  # already have a non-null value for this field
            new_props[new_key] = value
        feat["properties"] = new_props

    out_path = path  # overwrite the merged file in place
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    final_cols = sorted({k for feat in data["features"] for k in feat["properties"]})
    print(f"  updated {filename} in place  ({len(data['features']):,} features)")
    print(f"  final columns: {final_cols}")


if __name__ == "__main__":
    for fname in FILES:
        fix_file(fname)