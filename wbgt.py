"""
Tokyo Open Data Hackathon 2026 — Heat Stroke Prevention Project
WBGT (Heat Index) Station Data — Cleaning + Analysis

Source: Ministry of Environment Heat Stroke Prevention Site
        (wbgt.env.go.jp) — Tokyo station (point 44132), hourly real
        measurements, April 2018 - July 2026.

Outputs (written next to this script, in ./outputs/ and ./charts/):
  WBGT_Tokyo_clean.csv          - cleaned, English-column hourly data
                                   with a WBGT risk-level label added
  Analysis_WBGT_Yearly_Danger_Hours.csv
  charts/09_wbgt_yearly_danger_hours.png
  charts/10_wbgt_month_hour_heatmap.png
  charts/11_wbgt_summer_year_comparison.png
"""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "csv"
OUT_DIR = BASE_DIR / "cleaned_data"
CHART_DIR = BASE_DIR / "cleaned_data" / "charts"
OUT_DIR.mkdir(exist_ok=True)
CHART_DIR.mkdir(exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150, "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
})


# LOAD — the file has 7 metadata header rows before the real column header
raw = pd.read_csv(DATA_DIR / "wbgt.csv", encoding="shift_jis", skiprows=7)
raw.columns = ["date", "time", "quality_flag", "wbgt_c", "wet_bulb_temp_c",
               "black_globe_temp_c"]

raw["datetime"] = pd.to_datetime(raw["date"] + " " + raw["time"])
raw["year"] = raw["datetime"].dt.year
raw["month"] = raw["datetime"].dt.month
raw["hour"] = raw["datetime"].dt.hour

# quality_flag: 4 = confirmed real measured value (per Ministry of
# Environment's data service manual) — flag any rows that AREN'T this so
# you know if a future re-download ever includes estimated/gap-filled rows
n_non_measured = (raw["quality_flag"] != 4).sum()
print(f"Rows with non-measured/quality-flagged values: {n_non_measured} "
      f"of {len(raw)}")


# WBGT risk level — Japan's standard 5-tier heat illness prevention scale
def risk_level(wbgt):
    if wbgt >= 31:
        return "Danger"
    elif wbgt >= 28:
        return "Severe Warning"
    elif wbgt >= 25:
        return "Warning"
    elif wbgt >= 21:
        return "Caution"
    else:
        return "Almost Safe"


raw["risk_level"] = raw["wbgt_c"].apply(risk_level)

clean = raw[["datetime", "date", "time", "year", "month", "hour",
             "quality_flag", "wbgt_c", "wet_bulb_temp_c",
             "black_globe_temp_c", "risk_level"]]
clean.to_csv(OUT_DIR / "WBGT_Tokyo_clean.csv", index=False)
print(f"Wrote WBGT_Tokyo_clean.csv ({len(clean):,} rows)")


# ANALYSIS 1 — "Danger" hours (WBGT >= 31, the top risk tier) per year.
# 2026 is a partial year (data through July 31 only) — flagged separately
# so it isn't misread as a full-year total.
danger_hours = (clean[clean["risk_level"] == "Danger"]
                 .groupby("year").size().rename("danger_hours").reset_index())
full_years = danger_hours[danger_hours["year"] < 2026]
partial_2026 = danger_hours[danger_hours["year"] == 2026]

danger_hours.to_csv(OUT_DIR / "Analysis_WBGT_Yearly_Danger_Hours.csv", index=False)
print("\nDanger-level (WBGT>=31) hours per year:")
print(danger_hours.to_string(index=False))

fig, ax = plt.subplots(figsize=(9, 5))
colors = ["#d1495b"] * len(full_years) + ["#f4a259"]  # 2026 shown differently
ax.bar(danger_hours["year"].astype(str), danger_hours["danger_hours"], color=colors)
ax.set_title("Hours per Year at WBGT 'Danger' Level (>=31°C)\n"
              "Orange = 2026 partial year (through July 31 only)",
              fontsize=12, fontweight="bold")
ax.set_ylabel("Hours")
fig.tight_layout()
fig.savefig(CHART_DIR / "09_wbgt_yearly_danger_hours.png")
plt.close(fig)


# ANALYSIS 2 — Month x Hour heatmap of average WBGT: when (season + time
# of day) is heat-stroke risk actually highest?
pivot = clean.pivot_table(index="month", columns="hour", values="wbgt_c",
                            aggfunc="mean")

fig, ax = plt.subplots(figsize=(12, 6))
im = ax.imshow(pivot, aspect="auto", cmap="YlOrRd")
ax.set_xticks(range(len(pivot.columns)))
ax.set_xticklabels(pivot.columns)
ax.set_yticks(range(len(pivot.index)))
ax.set_yticklabels([f"Month {m}" for m in pivot.index])
ax.set_xlabel("Hour of Day")
ax.set_title("Average WBGT by Month & Hour (2018-2026)\n"
              "Darkest red = highest heat-stroke risk window",
              fontsize=12, fontweight="bold")
fig.colorbar(im, ax=ax, label="Average WBGT (°C)")
fig.tight_layout()
fig.savefig(CHART_DIR / "10_wbgt_month_hour_heatmap.png")
plt.close(fig)

peak_month = pivot.mean(axis=1).idxmax()
peak_hour = pivot.mean(axis=0).idxmax()
print(f"\nHighest-risk month (avg): Month {peak_month}")
print(f"Highest-risk hour of day (avg): {peak_hour}:00")


# ANALYSIS 3 — Summer (Jul-Aug) average WBGT by year — the clearest
# year-over-year comparison for your El Nino narrative
summer = clean[clean["month"].isin([7, 8])]
summer_yearly = summer.groupby("year")["wbgt_c"].mean().reset_index()

fig, ax = plt.subplots(figsize=(9, 5))
colors = ["#d1495b"] * (len(summer_yearly) - 1) + ["#f4a259"]
ax.bar(summer_yearly["year"].astype(str), summer_yearly["wbgt_c"], color=colors)
ax.set_title("Average July-August WBGT by Year\n"
              "Orange = 2026 (partial: July only, no August data yet)",
              fontsize=12, fontweight="bold")
ax.set_ylabel("Average WBGT (°C)")
ax.set_ylim(summer_yearly["wbgt_c"].min() - 1, summer_yearly["wbgt_c"].max() + 1)
fig.tight_layout()
fig.savefig(CHART_DIR / "11_wbgt_summer_year_comparison.png")
plt.close(fig)

print("\nAverage Jul-Aug WBGT by year:")
print(summer_yearly.to_string(index=False))

print(f"\nDone. Files written to {OUT_DIR} and {CHART_DIR}")