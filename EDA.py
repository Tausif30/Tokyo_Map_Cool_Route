"""
Reads the CLEANED English CSVs (produced by Analysis.py) plus the tree
GeoJSON (produced by Map_Data.py) and generates a set of presentation-ready
charts (PNG, 150 DPI) that build a decision narrative:
  1. Is Tokyo actually getting hotter?            -> chart 1
  2. When during the year is the risk highest?     -> chart 2
  3. Which wards have the least green relief?      -> chart 3
  4. Which wards have the fewest shade trees?       -> chart 4
  5. Where do both problems overlap (priority zones)? -> chart 5
  6. How "hardscaped" (paved/built) is each ward?  -> chart 6
  7. What tree species dominate the canopy?         -> chart 7
  8. Is winter itself shrinking (extra warming evidence)? -> chart 8

RUN ORDER: Map_Data.py -> Analysis.py -> Green_Data_Fix_Columns.py ->
Value_Fix.py -> EDA.py (this script). Chart 7 reads the fully mojibake-
fixed tree layer (Street_Trees_final.geojson) rather than the raw
Map_Data.py output, since species names are exactly the kind of field that
can come out garbled from the GIS-sourced shapefile rows — so it needs the
full Pipeline B chain to have already run, not just Map_Data.py.
"""

import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

BASE_DIR = Path(__file__).parent
IN_DIR = BASE_DIR / "cleaned_data"          # cleaned CSVs from Analysis.py
MAP_DIR = BASE_DIR / "outputs"              # GeoJSON layers from Map_Data.py / Pipeline B
OUT_DIR = BASE_DIR / "cleaned_data" / "charts"  # PNGs will be written here
OUT_DIR.mkdir(exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150, "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
})

# The 23 special wards only (excludes Tama cities, islands, and the
# jointly-administered "Central Breakwater" reclaimed-land parcel) — used
# to keep ward-comparison charts focused on the dense urban core where
# heat-island effects are strongest.
WARDS_23 = [
    "Chiyoda-ku", "Chuo-ku", "Minato-ku", "Shinjuku-ku", "Bunkyo-ku",
    "Taito-ku", "Sumida-ku", "Koto-ku", "Shinagawa-ku", "Meguro-ku",
    "Ota-ku", "Setagaya-ku", "Shibuya-ku", "Nakano-ku", "Suginami-ku",
    "Toshima-ku", "Kita-ku", "Arakawa-ku", "Itabashi-ku", "Nerima-ku",
    "Adachi-ku", "Katsushika-ku", "Edogawa-ku",
]


# CHART 1 — Is Tokyo actually getting hotter? (75-year annual temp trend)
temp_trend = pd.read_csv(IN_DIR / "Analysis_Annual_Temp_Trend.csv")

fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(temp_trend["year"], temp_trend["avg_temp_c"], marker="o", color="#d1495b")
ax.set_title("Tokyo's Annual Average Temperature Has Risen 2.5°C Since 1950",
              fontsize=13, fontweight="bold")
ax.set_xlabel("Year")
ax.set_ylabel("Average Temperature (°C)")
start, end = temp_trend.iloc[0], temp_trend.iloc[-1]
ax.annotate(f"{start.avg_temp_c}°C", (start.year, start.avg_temp_c),
            textcoords="offset points", xytext=(0, -18))
ax.annotate(f"{end.avg_temp_c}°C", (end.year, end.avg_temp_c),
            textcoords="offset points", xytext=(0, 10), fontweight="bold")
fig.tight_layout()
fig.savefig(OUT_DIR / "01_annual_temperature_trend.png")
plt.close(fig)


# CHART 2 — When during the year is heat risk highest? (2024 monthly temp
# vs precipitation, dual axis — high temp + low rain = highest WBGT risk)
t7 = pd.read_csv(IN_DIR / "1_7_Average_Temperature_by_Observatory_clean.csv")
t8 = pd.read_csv(IN_DIR / "1_8_Precipitation_at_Local_Meteorological_Stations_clean.csv")
tokyo_temp = t7[t7["observatory_en"] == "Tokyo"].iloc[0]
tokyo_precip = t8[t8["observatory_en"] == "Tokyo"].iloc[0]

months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
temps_2024 = [tokyo_temp[f"temp_2024_{m.lower()}_c"] for m in months]
precip_2024 = [tokyo_precip[f"precip_{m.lower()}_mm"] for m in months]

fig, ax1 = plt.subplots(figsize=(10, 5))
ax2 = ax1.twinx()
ax2.bar(months, precip_2024, color="#a3cef1", label="Precipitation (mm)", zorder=1)
ax1.plot(months, temps_2024, color="#d1495b", marker="o", linewidth=2.5,
          zorder=2, label="Avg Temperature (°C)")
ax1.set_ylabel("Average Temperature (°C)", color="#d1495b")
ax2.set_ylabel("Precipitation (mm)", color="#5b9bd5")
ax1.set_title("2024: Peak Heat (Jul–Aug) Coincides With Lower Rainfall\n"
              "→ Highest heat-stroke risk window", fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig(OUT_DIR / "02_monthly_temp_vs_precipitation_2024.png")
plt.close(fig)


# CHART 3 — Which of the 23 wards have the least park/green relief?
green = pd.read_csv(IN_DIR / "Analysis_Ward_Green_Coverage.csv")
green_23 = green[green["district_en"].isin(WARDS_23)].sort_values("green_ratio_pct")

fig, ax = plt.subplots(figsize=(9, 7))
colors = ["#d1495b" if v < green_23["green_ratio_pct"].median() else "#5b9bd5"
          for v in green_23["green_ratio_pct"]]
ax.barh(green_23["district_en"], green_23["green_ratio_pct"], color=colors)
ax.set_title("Park Coverage by Ward — Red Wards Have Below-Median Green Relief",
              fontsize=13, fontweight="bold")
ax.set_xlabel("Designated Park Area (% of Ward Land Area)")
fig.tight_layout()
fig.savefig(OUT_DIR / "03_ward_green_coverage.png")
plt.close(fig)

# CHART 4 — Which wards have the fewest street trees (shade) per km²?
density = pd.read_csv(IN_DIR / "Analysis_Ward_Tree_Density.csv")
density_23 = density[density["district_en"].isin(WARDS_23)].sort_values("trees_per_km2")

fig, ax = plt.subplots(figsize=(9, 7))
colors = ["#d1495b" if v < density_23["trees_per_km2"].median() else "#5b9bd5"
          for v in density_23["trees_per_km2"]]
ax.barh(density_23["district_en"], density_23["trees_per_km2"], color=colors)
ax.set_title("Street Tree Density by Ward — Red Wards Have Below-Median Shade",
              fontsize=13, fontweight="bold")
ax.set_xlabel("Street Trees per km²")
fig.tight_layout()
fig.savefig(OUT_DIR / "04_ward_tree_density.png")
plt.close(fig)


# CHART 5 — Priority map: wards weak on BOTH parks AND street trees
combo = green_23.merge(density_23, on="district_en")
med_green = combo["green_ratio_pct"].median()
med_tree = combo["trees_per_km2"].median()

fig, ax = plt.subplots(figsize=(9, 7))
ax.scatter(combo["green_ratio_pct"], combo["trees_per_km2"], s=80, color="#333")
for _, row in combo.iterrows():
    ax.annotate(row["district_en"].replace("-ku", ""),
                (row["green_ratio_pct"], row["trees_per_km2"]),
                fontsize=8, xytext=(4, 4), textcoords="offset points")
ax.axvline(med_green, color="gray", linestyle="--", linewidth=1)
ax.axhline(med_tree, color="gray", linestyle="--", linewidth=1)
ax.axvspan(0, med_green, ymin=0, ymax=(med_tree - ax.get_ylim()[0]) /
           (ax.get_ylim()[1] - ax.get_ylim()[0]), color="#d1495b", alpha=0.08)
ax.set_xlabel("Park Coverage (%)")
ax.set_ylabel("Street Tree Density (trees/km²)")
ax.set_title("Priority Zones: Bottom-Left = Low Parks AND Low Tree Shade",
              fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig(OUT_DIR / "05_priority_wards_scatter.png")
plt.close(fig)

priority_wards = combo[(combo["green_ratio_pct"] < med_green) &
                        (combo["trees_per_km2"] < med_tree)]["district_en"].tolist()


# CHART 6 — How "hardscaped" is each ward? (land use composition, % stacked)
land_use = pd.read_csv(IN_DIR / "1_2_Land_Use_by_District_clean.csv")
lu_23 = land_use[land_use["district_en"].isin(WARDS_23)].copy()
for col in ["residential_ha", "parks_ha", "roads_total_ha", "farmland_ha",
            "water_rivers_canals_ha", "forests_ha"]:
    lu_23[col.replace("_ha", "_pct")] = lu_23[col] / lu_23["total_ha"] * 100
lu_23 = lu_23.sort_values("residential_pct", ascending=False)

fig, ax = plt.subplots(figsize=(11, 7))
bottom = pd.Series([0] * len(lu_23), index=lu_23.index)
layers = [("residential_pct", "Residential", "#8c8c8c"),
          ("roads_total_pct", "Roads", "#4d4d4d"),
          ("parks_pct", "Parks", "#5b9bd5"),
          ("forests_pct", "Forest", "#2e7d32"),
          ("farmland_pct", "Farmland", "#a3d977"),
          ("water_rivers_canals_pct", "Water", "#a3cef1")]
for col, label, color in layers:
    ax.bar(lu_23["district_en"], lu_23[col], bottom=bottom, label=label, color=color)
    bottom += lu_23[col]
ax.set_title("Land Use Composition by Ward — Grey = Hardscape (Heat-Retaining)",
              fontsize=13, fontweight="bold")
ax.set_ylabel("% of Ward Land Area")
ax.legend(loc="upper right", ncol=2, fontsize=9)
plt.xticks(rotation=75, ha="right")
fig.tight_layout()
fig.savefig(OUT_DIR / "06_ward_land_use_composition.png")
plt.close(fig)


# CHART 7 — Which tree species dominate the citywide canopy?
trees = gpd.read_file(MAP_DIR / "Street_Trees_merged.geojson")
top_species = trees["species"].value_counts().head(15)

fig, ax = plt.subplots(figsize=(9, 7))
ax.barh(top_species.index[::-1], top_species.values[::-1], color="#2e7d32")
ax.set_title(f"Top 15 Street Tree Species Citywide (of {len(trees):,} records)",
              fontsize=13, fontweight="bold")
ax.set_xlabel("Number of Trees")
fig.tight_layout()
fig.savefig(OUT_DIR / "07_top_tree_species.png")
plt.close(fig)


# CHART 8 — Is winter itself shrinking? (secondary warming evidence)
seasons = pd.read_csv(IN_DIR / "1_9_Seasonal_Phenomenon_clean.csv")
seasons["first_frost_date"] = pd.to_datetime(seasons["first_frost_date"])
seasons["last_frost_date"] = pd.to_datetime(seasons["last_frost_date"])
# Express "first frost" as day-of-year-from-July so later dates plot higher
seasons["first_frost_doy"] = seasons["first_frost_date"].dt.dayofyear
seasons.loc[seasons["first_frost_date"].dt.month < 7, "first_frost_doy"] += 365

fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(seasons["year"], seasons["first_frost_doy"], marker="o", color="#5b9bd5")
ax.set_title("First Frost of the Year Is Arriving Later Over Time",
              fontsize=13, fontweight="bold")
ax.set_xlabel("Year")
ax.set_ylabel("Day of Year (first frost)")
fig.tight_layout()
fig.savefig(OUT_DIR / "08_first_frost_trend.png")
plt.close(fig)


print("Charts written to:", OUT_DIR)
for f in sorted(OUT_DIR.glob("*.png")):
    print(" -", f.name)
print(f"\nPriority wards (below-median parks AND below-median tree density):")
print(" ", ", ".join(priority_wards))