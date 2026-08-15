"""
Statistical yearbook cleaning + ward-level analysis script

What this does:
  1. Loads all 9 Tokyo Statistical Yearbook tables (land & climate)
  2. Cleans everything: fixes encodings, strips footer text, translates
     every column header to English, coerces text-junk ("-", "…") to
     proper NaN so numeric columns behave
  3. Saves ONE clean English CSV per input table
  4. Runs the ward-level heat analysis (green coverage %, tree density,
     75-year temperature trend)

Input files expected in csv/:
  1_1_Land_Area_by_District.csv
  1_2_Land_Use_by_District.csv
  1_3_Land_Area_by_District_and_Category.csv
  1_4_Land_Use_by_City_Planning_Areas.csv
  1_5_Land_Ownership_by_Municipality_and_Owner.csv
  1_6_Climate_Overview.csv
  1_7_Average_Temperature_by_Observatory.csv
  1_8_Precipitation_at_Local_Meteorological_Stations.csv
  1_9_Seasonal_Phenomenon.csv

Cleaned yearbook CSVs + ward-level Analysis_*.csv outputs are written to cleaned_data/
"""

import pandas as pd
import geopandas as gpd
from pathlib import Path

DATA_DIR = Path(r"E:\Tokyo_Metropolitan_Project\csv")
OUT_DIR = Path(r"E:\Tokyo_Metropolitan_Project\cleaned_data")
MAP_DIR = Path(r"E:\Tokyo_Metropolitan_Project\outputs")  # Map_Data.py's output folder
OUT_DIR.mkdir(exist_ok=True)

# Placeholder tokens the yearbook uses for "no data" — convert to NaN
NA_TOKENS = ["-", "…", "－", ""]


# Generic cleaner for the 9 statistical yearbook tables.
# Every one of these files follows the same template: a header row, data
# rows, then a blank separator row, then Japanese/English footnotes. This
# renames columns to plain English, trims the footer, and coerces numeric
# columns.
def clean_yearbook_table(filename, new_columns, text_columns, out_name):
    df = pd.read_csv(DATA_DIR / filename, encoding="utf-8-sig", na_values=NA_TOKENS)
    df.columns = new_columns[: len(df.columns)]

    # Drop the footer: the yearbook template has a fully-blank row right
    # after the last real data row, followed by footnote text.
    blank_mask = df.isna().all(axis=1)
    if blank_mask.any():
        df = df.iloc[: blank_mask.idxmax()]

    # Drop any unnamed leftover columns from trailing commas in the source
    df = df.loc[:, ~df.columns.str.startswith("extra")]

    # Coerce everything that isn't explicitly a text/date column to numeric
    for col in df.columns:
        if col not in text_columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df.to_csv(OUT_DIR / out_name, index=False)
    print(f"  wrote {out_name}  ({len(df)} rows, {len(df.columns)} cols)")
    return df



# 1-1  Land Area by District
land_area = clean_yearbook_table(
    "1_1_Land_Area_by_District.csv",
    new_columns=["era_year", "year", "admin_level", "area_code",
                 "district_jp", "district_en", "mark",
                 "area_km2", "permillage_pct"],
    text_columns=["era_year", "district_jp", "district_en", "mark"],
    out_name="1_1_Land_Area_by_District_clean.csv",
)


# 1-2  Land Use by District  (units: hectares, per source magnitude)
land_use = clean_yearbook_table(
    "1_2_Land_Use_by_District.csv",
    new_columns=["admin_level", "area_code", "district_jp", "district_en", "mark",
                 "total_ha", "residential_ha", "other_use_ha",
                 "other_use_outdoor_ha", "parks_ha", "unused_land_ha",
                 "roads_total_ha", "roads_of_which_roads_ha", "farmland_ha",
                 "water_rivers_canals_ha", "forests_ha", "fields_ha"],
    text_columns=["district_jp", "district_en", "mark"],
    out_name="1_2_Land_Use_by_District_clean.csv",
)


# 1-3  Land Area by District and Category (tax-assessment categories, ha)
clean_yearbook_table(
    "1_3_Land_Area_by_District_and_Category.csv",
    new_columns=["era_year", "year", "admin_level", "area_code",
                 "district_jp", "district_en",
                 "total_ha", "land_for_buildings_total_ha",
                 "commercial_district_ha", "industrial_district_ha",
                 "residential_district_ha", "other_building_land_ha",
                 "paddy_fields_ha", "ordinary_fields_ha", "forests_ha",
                 "waste_land_ha", "ponds_swamps_ha", "misc_land_ha",
                 "land_under_tax_exemption_ha"],
    text_columns=["era_year", "district_jp", "district_en"],
    out_name="1_3_Land_Area_by_District_and_Category_clean.csv",
)


# 1-4  Land Use by City Planning Areas (zoning, ha)
clean_yearbook_table(
    "1_4_Land_Use_by_City_Planning_Areas.csv",
    new_columns=["era_year", "year", "admin_level", "area_code",
                 "district_jp", "district_en",
                 "city_planning_area_ha", "urbanization_promotion_area_ha",
                 "urbanization_control_area_ha", "use_zoning_total_ha",
                 "low_rise_residential_cat1_ha", "low_rise_residential_cat2_ha",
                 "mid_high_residential_cat1_ha", "mid_high_residential_cat2_ha",
                 "residential_cat1_ha", "residential_cat2_ha",
                 "quasi_residential_ha", "neighborhood_commercial_ha",
                 "commercial_ha", "quasi_industrial_ha", "industrial_ha",
                 "exclusive_industrial_ha"],
    text_columns=["era_year", "district_jp", "district_en"],
    out_name="1_4_Land_Use_by_City_Planning_Areas_clean.csv",
)


# 1-5  Land Ownership by Municipality and Owner (2023, ha)
clean_yearbook_table(
    "1_5_Land_Ownership_by_Municipality_and_Owner.csv",
    new_columns=["admin_level", "area_code", "district_jp", "district_en", "mark",
                 "total_owners", "total_area_ha",
                 "individual_owners", "individual_area_ha",
                 "company_owners", "company_area_ha"],
    text_columns=["district_jp", "district_en", "mark"],
    out_name="1_5_Land_Ownership_by_Municipality_and_Owner_clean.csv",
)


# 1-6  Climate Overview (1950–2024, annual + monthly rows)
climate = clean_yearbook_table(
    "1_6_Climate_Overview.csv",
    new_columns=["era_year", "year", "month_jp", "month",
                 "avg_sea_level_pressure_hpa", "avg_temp_c",
                 "avg_high_temp_c", "avg_low_temp_c", "avg_humidity_pct",
                 "min_humidity_pct", "min_humidity_date", "avg_cloud_amount",
                 "sunshine_hours", "sunshine_pct", "avg_wind_speed_ms",
                 "max_wind_speed_ms", "max_wind_direction", "max_wind_date",
                 "total_precip_mm", "max_daily_precip_mm", "max_daily_precip_date",
                 "days_precip_ge_0_5mm", "days_precip_ge_1_0mm",
                 "days_precip_ge_10mm", "days_precip_ge_30mm",
                 "days_clear", "days_cloudy", "days_rainy", "days_snowy",
                 "days_snow_cover", "days_fog", "days_thunderstorm",
                 "days_no_sunshine", "days_wind_ge_10ms", "earthquake_count",
                 "extra1", "extra2"],
    text_columns=["era_year", "month_jp", "month", "min_humidity_date",
                  "max_wind_direction", "max_wind_date", "max_daily_precip_date"],
    out_name="1_6_Climate_Overview_clean.csv",
)


# 1-7  Average Temperature by Observatory (wide format, one row per station)
clean_yearbook_table(
    "1_7_Average_Temperature_by_Observatory.csv",
    new_columns=["observatory_jp", "observatory_en",
                 "avg_temp_2020_c", "avg_temp_2021_c", "avg_temp_2022_c",
                 "avg_temp_2023_c", "avg_temp_2024_c",
                 "temp_2024_jan_c", "temp_2024_feb_c", "temp_2024_mar_c",
                 "temp_2024_apr_c", "temp_2024_may_c", "temp_2024_jun_c",
                 "temp_2024_jul_c", "temp_2024_aug_c", "temp_2024_sep_c",
                 "temp_2024_oct_c", "temp_2024_nov_c", "temp_2024_dec_c"],
    text_columns=["observatory_jp", "observatory_en"],
    out_name="1_7_Average_Temperature_by_Observatory_clean.csv",
)


# 1-8  Precipitation at Local Meteorological Stations (2024, monthly)
clean_yearbook_table(
    "1_8_Precipitation_at_Local_Meteorological_Stations.csv",
    new_columns=["observatory_jp", "observatory_en", "mark", "total_precip_mm",
                 "precip_jan_mm", "precip_feb_mm", "precip_mar_mm",
                 "precip_apr_mm", "precip_may_mm", "precip_jun_mm",
                 "precip_jul_mm", "precip_aug_mm", "precip_sep_mm",
                 "precip_oct_mm", "precip_nov_mm", "precip_dec_mm"],
    text_columns=["observatory_jp", "observatory_en", "mark"],
    out_name="1_8_Precipitation_at_Local_Meteorological_Stations_clean.csv",
)


# 1-9  Seasonal Phenomenon (first/last frost, snow, freezing dates)
clean_yearbook_table(
    "1_9_Seasonal_Phenomenon.csv",
    new_columns=["era_year", "year", "first_frost_date", "last_frost_date",
                 "first_snow_date", "last_snow_date",
                 "first_freeze_date", "last_freeze_date"],
    text_columns=["era_year", "first_frost_date", "last_frost_date",
                  "first_snow_date", "last_snow_date",
                  "first_freeze_date", "last_freeze_date"],
    out_name="1_9_Seasonal_Phenomenon_clean.csv",
)

print()

# STREET TREES — no longer loaded from CSV here. Map_Data.py owns tree data
# end to end now (CSV + GIS shapefile sources merged into one GeoJSON); we
# just read its output back in for the ward-density analysis below.
tree_geojson = MAP_DIR / "Street_Trees.geojson"
if not tree_geojson.exists():
    raise FileNotFoundError(
        f"{tree_geojson} not found — run Map_Data.py first, it produces the "
        "tree data this script's ward-density analysis depends on."
    )
trees_gdf = gpd.read_file(tree_geojson)
print(f"  read {len(trees_gdf):,} street tree features from {tree_geojson.name}")

print("\n=== Cleaning complete. Running ward-level heat analysis... ===\n")


# ANALYSIS 1 — Green coverage % by ward (parks / total ward area)
land_area_2024 = land_area[land_area["year"] == 2024]
ward_profile = land_area_2024.merge(land_use, on="district_en", how="inner",
                                     suffixes=("_area", "_use"))
ward_profile["green_ratio_pct"] = (
    ward_profile["parks_ha"] / ward_profile["total_ha"] * 100
).round(2)
ward_profile.to_csv(OUT_DIR / "Analysis_Ward_Green_Coverage.csv", index=False)

print("Ward green-space ratio — least green 5 / most green 5:")
ranked = ward_profile[["district_en", "green_ratio_pct"]].sort_values("green_ratio_pct")
print(ranked.head(5).to_string(index=False))
print(ranked.tail(5).to_string(index=False))
print("(Note: 'parks_ha' = designated parks only, not total greenery/forest —")
print(" rural wards score low here despite having lots of natural forest.)\n")


# ANALYSIS 2 — Street tree density per km² by ward (23 wards only — Tama
# trees have no ward field in the source data)
tree_counts = (trees_gdf[trees_gdf["ward"].notna()]
               .groupby("ward").size().rename("tree_count").reset_index())
# 'ward' here is still in Japanese (from the 23-ward source file) — map to
# English district names via the district_jp/district_en lookup
ward_lookup = land_area[["district_jp", "district_en"]].drop_duplicates()
tree_counts = tree_counts.merge(ward_lookup, left_on="ward", right_on="district_jp")
density = tree_counts.merge(land_area_2024[["district_en", "area_km2"]],
                             on="district_en", how="left")
density["trees_per_km2"] = (density["tree_count"] / density["area_km2"]).round(1)
density = density.sort_values("trees_per_km2", ascending=False)
density[["district_en", "tree_count", "area_km2", "trees_per_km2"]].to_csv(
    OUT_DIR / "Analysis_Ward_Tree_Density.csv", index=False)

print("Street tree density by ward (top 5):")
print(density[["district_en", "trees_per_km2"]].head(5).to_string(index=False))
print()


# ANALYSIS 3 — Historical annual temperature trend, 1950-2024
annual = climate[climate["month_jp"] == "総数"].dropna(subset=["avg_temp_c"])
annual[["year", "avg_temp_c"]].to_csv(OUT_DIR / "Analysis_Annual_Temp_Trend.csv",
                                        index=False)
print(f"Annual avg temperature: {annual['avg_temp_c'].iloc[0]}°C "
      f"({int(annual['year'].iloc[0])}) -> "
      f"{annual['avg_temp_c'].iloc[-1]}°C ({int(annual['year'].iloc[-1])})")

print(f"\n=== All outputs written to {OUT_DIR} ===")
for f in sorted(OUT_DIR.glob("*clean*")) + sorted(OUT_DIR.glob("Analysis_*")):
    print(" -", f.name)