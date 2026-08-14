"""
Fix mojibake VALUES (not just column names) + add category colors

Pipeline B, stage 3 of 3:
  Map_Data.py (writes *_merged.geojson)
    -> Map_Data_Fix_Columns.py (fixes *_merged.geojson IN PLACE)
    -> Value_Fix.py -> Replaces the Original Files with the new one with no new naming convention.


Follow-up to Map_Data_Fix_Columns.py, which now fixes column NAMES in
place on the *_merged.geojson files (it used to spin off a separate
*_clean.geojson — no longer does, one less file to track). This script
reads those same *_merged.geojson files and fixes the encoding problem
where it also corrupted VALUES inside features. A given
source shapefile's corrupted values could end up in any of the 5 files
depending on what it contains — so this scans all 5 rather than a
hardcoded subset. The detection heuristic only touches values that
actually look garbled, so it's harmless to run on files that turn out to
be clean.

Also adds a "marker-color" property (simplestyle-spec, recognized by
geojson.io, GitHub previews, and many GIS tools) plus a plain "color_hex"
property, so points/lines render in distinct colors by category without
manual styling.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
FILES = [
    "Water_Canals_merged.geojson",
    "Street_Trees_merged.geojson",
    "Parks_Green_Spaces_merged.geojson",
    "Protected_Green_Spaces_merged.geojson",
    "Drinking_Stations_merged.geojson",
]

# Distinct, high-contrast color per category (hex) — one entry per category
# Map_Data.py can produce. Add an entry here if you re-enable another
# category folder in Map_Data.py.
CATEGORY_COLORS = {
    "Water & Canals": "#1976d2",
    "Street Trees": "#8bc34a",
    "Parks & Green Spaces": "#2e7d32",
    "Protected Green Spaces": "#66bb6a",
    "Drinking Stations": "#00bcd4",
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

for filename in FILES:
    path = BASE_DIR / filename
    if not path.exists():
        print(f"Skipping {filename} (not found)")
        continue

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    fixed_count = 0
    for feat in data["features"]:
        props = feat["properties"]
        for key, val in props.items():
            recovered = recover_value(val)
            if recovered != val:
                props[key] = recovered
                fixed_count += 1

        # Color coding for visualization
        color = CATEGORY_COLORS.get(props.get("category"), "#999999")
        props["marker-color"] = color   # simplestyle-spec (geojson.io, GitHub)
        props["color_hex"] = color      # plain field, for QGIS/other tools
    with open(BASE_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"{filename}: recovered {fixed_count} garbled values, "
          f"wrote {filename}")