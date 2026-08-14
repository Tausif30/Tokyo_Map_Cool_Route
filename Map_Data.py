"""
Turn raw CSVs + GIS shapefiles into 5 clean-ish, English, WGS84
GeoJSON layers. This absorbs work that used to be split across two files:
  - Analysis.py used to build the street-tree and drinking-water GeoJSONs
    from the yearbook CSVs.
  - Green_Data.py used to scan the Green Open Data shapefiles.
Both of those code paths now live here instead, so Analysis.py only does
statistical-yearbook cleaning, and Green_Data.py is retired (nothing left
in it that isn't also here).

OUTPUT — 5 files, one per category, written to outputs/:
  1. Water_Canals_merged.geojson       (rivers, canals, waterworks, lakes,
                                         tidal flats, springs)
  2. Street_Trees_merged.geojson       (every point/line street-tree record
                                         we have — see note below)
  3. Parks_Green_Spaces_merged.geojson
  4. Protected_Green_Spaces_merged.geojson
  5. Drinking_Stations_merged.geojson

RUN ORDER: this script has no dependencies on the others and should run
FIRST. Analysis.py (tree-density-by-ward) and EDA.py (chart 7, top tree
species) both read this script's output, so run Map_Data.py before either
of them.
"""

import pandas as pd
import geopandas as gpd
from pathlib import Path

BASE_DIR = Path(__file__).parent
CSV_DIR = BASE_DIR / "csv"
OUT_DIR = BASE_DIR / "outputs"
OUT_DIR.mkdir(exist_ok=True)


# Shapefile category folders to scan: folder name -> English category.
# Only these 4 folders are walked — see module docstring.
CATEGORY_MAP = {
    "Water_Canals": "Water & Canals",
    "Street_Trees": "Street Trees",
    "Parks_Green_Spaces": "Parks & Green Spaces",
    "Protected_Green_Areas": "Protected Green Spaces",
}

# category -> output filename. Kept separate from CATEGORY_MAP so category
# names and file names can change independently. To split Street Trees back
# into two files (csv vs gis), give the gis_shapefile rows their own
# category below instead of reusing "Street Trees".
OUTPUT_FILES = {
    "Water & Canals": "Water_Canals_merged.geojson",
    "Street Trees": "Street_Trees_merged.geojson",
    "Parks & Green Spaces": "Parks_Green_Spaces_merged.geojson",
    "Protected Green Spaces": "Protected_Green_Spaces_merged.geojson",
    "Drinking Stations": "Drinking_Stations_merged.geojson",
}

# Japanese subfolder/filename fragment -> English label. Pruned to just the
# 4 scanned categories (the full original list had ~38 entries covering all
# 9 categories — add entries back here if you re-enable a folder above).
LABEL_MAP = {
    "河川": "River/Canal", "上水": "Waterworks/Irrigation",
    "湖沼": "Lake/Marsh", "干潟": "Tidal Flat", "湧水": "Spring",
    "街路樹": "Street Trees",
    "都立公園": "Metropolitan Park", "区市町村立公園": "Municipal Park",
    "国営公園": "National Park", "海上公園": "Marine Park",
    "自然ふれあい公園": "Nature Park", "国民公園": "National Garden",
    "都市公園に準ずるもの": "Quasi-Urban Park", "植物園": "Botanical/Zoo/Aquarium",
    "庭園": "Japanese Garden", "霊園": "Cemetery",
    "東京都保全地域": "TMG Conservation Area", "保存樹林": "Preserved Forest",
    "保存樹木": "Preserved Tree/Hedge", "農の風景育成地区": "Agricultural Landscape District",
    "都民の森": "Citizens' Forest",
}

# Japanese DBF field name -> English column name. Left as the FULL original
# set (unpruned) — these are generic enough to show up in any category's
# attribute table, and we have no visibility into which DBF fields the 4
# remaining folders actually use, so pruning risks silently breaking a
# translation that used to work.
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


def translate_label(name):
    for jp, en in LABEL_MAP.items():
        if jp in name:
            return en
    return name  # unmatched — keep original so gaps are visible


def translate_columns(gdf):
    rename_map, unmatched = {}, []
    for col in gdf.columns:
        if col == "geometry":
            continue
        english = FIELD_TRANSLATIONS.get(col)
        if english:
            rename_map[col] = english
        elif any(ord(ch) > 127 for ch in col):
            unmatched.append(col)
    if unmatched:
        print(f"(untranslated columns, add to FIELD_TRANSLATIONS: {unmatched})")
    return gdf.rename(columns=rename_map)



# GIS shapefiles — walk the 4 category folders. Points + lines only; any
# Polygon/MultiPolygon layer is read (so it can be logged) then dropped.
def load_shapefiles(base_dir):
    kept, skipped_polygons = [], []
    for shp_path in sorted(base_dir.rglob("*.shp")):
        top_folder = shp_path.relative_to(base_dir).parts[0]
        if top_folder not in CATEGORY_MAP:
            continue
        category = CATEGORY_MAP[top_folder]
        subcategory = translate_label(shp_path.stem)

        # Most of Tokyo's GIS shapefiles don't ship a .cpg file declaring
        # their encoding, so GDAL defaults to Latin-1 and garbles the
        # Shift-JIS (cp932) field names/values. Force cp932 explicitly —
        # if a particular file genuinely IS UTF-8, this will raise and we
        # fall back automatically.
        try:
            gdf = gpd.read_file(shp_path, encoding="cp932")
        except (UnicodeDecodeError, UnicodeEncodeError):
            gdf = gpd.read_file(shp_path, encoding="utf-8")
        except Exception as e:
            print(f"  FAILED to read {shp_path}: {e}")
            continue

        if len(gdf) == 0:
            continue

        geom_type = gdf.geom_type.iloc[0]
        if geom_type in ("Polygon", "MultiPolygon"):
            skipped_polygons.append(
                f"{shp_path.relative_to(base_dir)}  ({len(gdf)} features, {geom_type})")
            continue

        gdf["category"] = category
        gdf["subcategory"] = subcategory
        gdf["source_file"] = shp_path.name
        gdf["source_dataset"] = "gis_shapefile"
        gdf = translate_columns(gdf)
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        kept.append(gdf)
        print(f"  loaded {shp_path.relative_to(base_dir)}  "
              f"({len(gdf)} features, geom={geom_type}, category={category})")

    if skipped_polygons:
        print(f"\n  Skipped {len(skipped_polygons)} polygon layer(s) (not used for now):")
        for s in skipped_polygons:
            print(f"    - {s}")

    return kept

# Street trees from the yearbook CSVs (23-wards Shift-JIS + Tama UTF-8) —
# this is the individual-tree-point data that used to live in Analysis.py
def load_csv_street_trees():
    trees_23ku = pd.read_csv(CSV_DIR / "Street_Trees_23_Wards.csv", encoding="shift_jis")
    trees_23ku = trees_23ku.rename(columns={
        "樹種": "species", "区分": "size_class", "樹高(m)": "height_m",
        "枝張(m)": "width_m", "幹周(cm）": "trunk_circumference_cm",
        "行政区": "ward", "経度": "longitude", "緯度": "latitude",
    })
    trees_23ku["source_area"] = "23_wards"

    trees_tama = pd.read_csv(CSV_DIR / "Street_Trees_Tama_Ward.csv", encoding="utf-8-sig")
    trees_tama = trees_tama.rename(columns={
        "name": "species", "type": "size_class", "height": "height_m",
        "width": "width_m", "perimeter": "trunk_circumference_cm",
    })
    trees_tama["ward"] = None  # Tama file has no ward field (route-based instead)
    trees_tama["source_area"] = "tama"

    tree_cols = ["species", "size_class", "height_m", "width_m",
                 "trunk_circumference_cm", "ward", "longitude", "latitude", "source_area"]
    trees_all = pd.concat([trees_23ku[tree_cols], trees_tama[tree_cols]], ignore_index=True)
    trees_all["category"] = "Street Trees"
    trees_all["subcategory"] = "Street Trees"
    trees_all["source_file"] = "Street_Trees_23_Wards.csv + Street_Trees_Tama_Ward.csv"
    trees_all["source_dataset"] = "yearbook_csv"

    gdf = gpd.GeoDataFrame(
        trees_all,
        geometry=gpd.points_from_xy(trees_all["longitude"], trees_all["latitude"]),
        crs="EPSG:4326",
    )
    print(f"  loaded street tree CSVs  ({len(gdf):,} trees)")
    return gdf

# Drinking water stations — from the yearbook CSV
def load_drinking_stations():
    water = pd.read_csv(CSV_DIR / "Drinking_Water_Station.csv", encoding="shift_jis")
    water = water.rename(columns={
        "緯度": "latitude", "経度": "longitude", "施設名": "facility_name",
        "所在地": "address", "水飲み栓設置場所": "tap_location",
        "営業時間": "hours", "入場料等": "fee", "タイプ": "fountain_type",
        "稼働停止": "out_of_service", "備考": "notes",
    })
    water["category"] = "Drinking Stations"
    water["subcategory"] = "Drinking Station"
    water["source_file"] = "Drinking_Water_Station.csv"
    water["source_dataset"] = "yearbook_csv"

    gdf = gpd.GeoDataFrame(
        water,
        geometry=gpd.points_from_xy(water["longitude"], water["latitude"]),
        crs="EPSG:4326",
    )
    print(f"  loaded drinking water stations  ({len(gdf)} stations)")
    return gdf



# Run everything, group by output category, write one GeoJSON each
if __name__ == "__main__":
    print("=== Loading GIS shapefiles (Water_Canals, Street_Trees, "
          "Parks_Green_Spaces, Protected_Green_Areas) ===")
    shape_layers = load_shapefiles(BASE_DIR)

    print("\nLoading CSV-sourced layers (street trees + drinking stations)")
    csv_trees = load_csv_street_trees()
    drinking = load_drinking_stations()

    by_category = {}
    for gdf in shape_layers:
        by_category.setdefault(gdf["category"].iloc[0], []).append(gdf)
    by_category.setdefault("Street Trees", []).append(csv_trees)
    by_category.setdefault("Drinking Stations", []).append(drinking)

    print("\nWriting GeoJSON layers")
    for category, out_name in OUTPUT_FILES.items():
        parts = by_category.get(category, [])
        if not parts:
            print(f"  (no features for {category} — skipping {out_name})")
            continue
        combined = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
        combined.to_file(OUT_DIR / out_name, driver="GeoJSON")
        print(f"  wrote {out_name}  ({len(combined):,} features, "
              f"geoms={sorted(combined.geom_type.unique())})")

    print(f"\GeoJSON layers written to {OUT_DIR}")
    print("NOTE: none of these layers carry a 'ward' field by default except")
    print("the yearbook-CSV-sourced Street Trees rows — you'll still need a")
    print("spatial join against ward boundaries (or check for a 所在区市町村")
    print("column) to get ward-level breakdowns out of the GIS-sourced rows.")