"""
============================================================================
Tokyo Open Data Hackathon 2026 — Heat Stroke Prevention Project
WBGT_Monitor.py — Pipeline C, script 2

Polls the Ministry of Environment's official real-time WBGT API for the
Tokyo station (44132 — same station wbgt.py already uses for the historical
bulk download) and raises an alert when the heat risk is high.

DATA SOURCE (verified against the Ministry's own API manual,
https://www.wbgt.env.go.jp/man15NH/wbgt_data_api_service_manual.pdf,
"暑さ指数（WBGT）実況値取得 API", published version dated 2026-06-24):
  GET https://www.wbgt.env.go.jp/api/v1/getSurveyData
      ?data_type=0&data_type=1        (0=estimated, 1=measured — request both,
                                        take whichever is most recent)
      &location_type=1                (1 = query by station number)
      &wbgt_nos=44132                 (Tokyo)
      &date_from=YYYYMMDDHHMMSS
      &date_to=YYYYMMDDHHMMSS
  Returns JSON: {"status": "success", "data": [{"wbgt_no":..., "wbgt_date":
  "YYYY/MM/DD HH:MM:SS", "wbgt_class": 0|1, "wbgt_WO": "<WBGT °C as string>",
  "wbgt_Tw":..., "wbgt_Tg":..., "wbgt_WI": "<data-quality flag 0-4>"}, ...]}
This endpoint is documented as free/open for this kind of use (the same
manual + wbgt_data_download.php page describe it as a public service for
sites/apps that want to republish WBGT data). Re-check the manual before
the hackathon demo in case the URL/params shift — Ministry pages have noted
mid-season API changes before.

WHAT THIS SCRIPT DOES ON EACH RUN:
  1. Fetch the last LOOKBACK_HOURS of survey data for station 44132.
  2. Take the most recent reading, classify it with the same 5-tier scale
     wbgt.py already uses on the historical data.
  3. Overwrite outputs/WBGT_Current_Status.json with the latest reading.
     *** This is the file your future web app should poll to show its own
     in-app banner/popup *** — a toast notification on someone's laptop is
     useless once this is a map people use on their phones; a small status
     JSON that ships to R2 alongside your other outputs (wrangler.py already
     walks outputs/ recursively, so no changes needed there) is what a real
     frontend can actually react to.
  4. Append a row to cleaned_data/WBGT_Live_Log.csv (a running trace of live
     polls — separate from wbgt.py's historical bulk file — useful later for
     an in-app "WBGT today" mini-chart).
  5. If the reading is Severe Warning or Danger: print a clear alert, and
     ALSO try a local desktop toast via `plyer` if it's installed, for
     demoing on your own machine (`pip install plyer`). This is best-effort;
     it's not the primary alert channel (see point 3).

SCHEDULING: this script does one poll and exits — run it on a timer.
  Windows: Task Scheduler, action = run this script every 15-30 min during
           daytime hours (Apr-Oct).
  Anything else: cron, or a GitHub Action on a schedule trigger. Since your
           pipeline already lives on Cloudflare, a Worker Cron Trigger that
           calls this same API and writes straight to R2 would remove the
           "does a laptop need to stay on" dependency entirely — worth
           doing once the Python version is proven out.

RUN ORDER: standalone — no dependency on the other Pipeline C scripts.
============================================================================
"""

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR / "outputs"
CLEAN_DIR = BASE_DIR / "cleaned_data"
OUT_DIR.mkdir(exist_ok=True)
CLEAN_DIR.mkdir(exist_ok=True)

STATUS_PATH = OUT_DIR / "WBGT_Current_Status.json"
LOG_PATH = CLEAN_DIR / "WBGT_Live_Log.csv"

API_URL = "https://www.wbgt.env.go.jp/api/v1/getSurveyData"
TOKYO_STATION = 44132
LOOKBACK_HOURS = 6   # widen this if the station has been dropping updates

ALERT_LEVELS = {"Severe Warning", "Danger"}


# Same 5-tier scale as wbgt.py's risk_level() — kept in sync manually since
# this script is meant to run standalone (e.g. via Task Scheduler) without
# importing wbgt.py's module-level script logic.
def risk_level(wbgt_c):
    if wbgt_c >= 31:
        return "Danger"
    elif wbgt_c >= 28:
        return "Severe Warning"
    elif wbgt_c >= 25:
        return "Warning"
    elif wbgt_c >= 21:
        return "Caution"
    else:
        return "Almost Safe"


def fetch_latest_reading():
    now = datetime.now()
    date_to = now.strftime("%Y%m%d%H%M%S")
    date_from = (now - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y%m%d%H%M%S")

    params = [
        ("data_type", "0"), ("data_type", "1"),
        ("location_type", "1"),
        ("wbgt_nos", str(TOKYO_STATION)),
        ("date_from", date_from),
        ("date_to", date_to),
    ]
    resp = requests.get(API_URL, params=params, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    if payload.get("status") != "success":
        raise RuntimeError(f"WBGT API returned an error: {payload.get('errMsg')}")

    records = [r for r in payload.get("data", []) if r.get("wbgt_WO") not in (None, "")]
    if not records:
        raise RuntimeError(
            f"WBGT API returned no usable records for station {TOKYO_STATION} "
            f"in the last {LOOKBACK_HOURS}h — station may be between "
            "seasonal operating dates, or LOOKBACK_HOURS needs widening."
        )

    records.sort(key=lambda r: r["wbgt_date"])
    latest = records[-1]
    return {
        "station": TOKYO_STATION,
        "prefecture": "Tokyo",
        "observed_at": latest["wbgt_date"],
        "data_type": "measured" if str(latest["wbgt_class"]) == "1" else "estimated",
        "data_quality_flag": latest.get("wbgt_WI"),
        "wbgt_c": round(float(latest["wbgt_WO"]), 1),
    }


def write_status(reading):
    level = risk_level(reading["wbgt_c"])
    status = {
        **reading,
        "risk_level": level,
        "alert": level in ALERT_LEVELS,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    return status


def append_log(status):
    is_new = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "checked_at", "observed_at", "station", "data_type",
            "wbgt_c", "risk_level", "alert",
        ])
        if is_new:
            writer.writeheader()
        writer.writerow({k: status[k] for k in writer.fieldnames})


def try_desktop_notification(status):
    try:
        from plyer import notification
    except ImportError:
        print("  (plyer not installed — skipping desktop popup. "
              "`pip install plyer` to enable it for local demos.)")
        return
    try:
        notification.notify(
            title=f"Heat Stroke Warning — WBGT {status['wbgt_c']}\u00b0C ({status['risk_level']})",
            message="High heat-stroke risk in Tokyo right now. Prefer shaded/"
                    "cool routes and take hydration breaks.",
            app_name="Tokyo Heat Stroke Prevention",
            timeout=15,
        )
    except Exception as e:
        print(f"  (desktop notification failed: {e})")


# ===========================================================================
# PERSONALIZED ALERTING
# ===========================================================================
# Deliberately NOT part of the polling loop above. The poller's only job is
# to fetch the one citywide WBGT reading and publish it once. Personalizing
# it per user happens here instead, as a plain function any number of
# requests can call with a different profile — that's what lets this scale
# to however many app users there are without the poller needing a
# subscriber list, device tokens, etc. (api.py calls this per-request.)
#
# "Increased caution" grouping (children, 65+, pregnancy, chronic
# condition -> alert one risk tier earlier than the general population)
# reflects the general pattern in Japan's public heat-stroke guidance that
# these groups are more heat-vulnerable and are advised to act sooner —
# it is NOT a medical guideline and shouldn't be presented as one in the
# UI. Treat the specific cutoffs (age 12 / 65) as an adjustable default,
# not an authoritative threshold, and make it easy for a user to see/edit
# their own profile.
RISK_TIER_ORDER = ["Almost Safe", "Caution", "Warning", "Severe Warning", "Danger"]

RECOMMENDED_ACTION = {
    "Almost Safe": "Low risk. Normal activity is fine — just stay hydrated.",
    "Caution": "Start drinking water regularly. Take breaks in shade during exercise.",
    "Warning": "Take regular rest breaks in shade or air conditioning. Avoid strenuous activity in direct sun.",
    "Severe Warning": "Avoid outdoor activity if possible. If you must go out, stay in shade, hydrate often, and rest frequently.",
    "Danger": "Avoid going outside. Stay in an air-conditioned space and hydrate.",
}


def _is_increased_caution(profile):
    age = profile.get("age")
    return bool(
        (age is not None and (age < 12 or age >= 65))
        or profile.get("is_pregnant")
        or profile.get("has_chronic_condition")
    )


def classify_for_profile(wbgt_c, profile=None):
    """profile: dict with optional 'age' (int), 'is_pregnant' (bool),
    'has_chronic_condition' (bool). None/{} = general-population defaults.
    Returns the measured level, the personalized ("effective") level, and
    a short plain-language recommended action for that effective level."""
    profile = profile or {}
    base_level = risk_level(wbgt_c)

    if _is_increased_caution(profile):
        idx = RISK_TIER_ORDER.index(base_level)
        effective_level = RISK_TIER_ORDER[min(idx + 1, len(RISK_TIER_ORDER) - 1)]
    else:
        effective_level = base_level

    return {
        "wbgt_c": wbgt_c,
        "measured_risk_level": base_level,
        "effective_risk_level": effective_level,
        "increased_caution_profile": _is_increased_caution(profile),
        "alert": effective_level in ALERT_LEVELS,
        "recommended_action": RECOMMENDED_ACTION[effective_level],
    }


if __name__ == "__main__":
    print(f"=== Polling WBGT for station {TOKYO_STATION} (Tokyo) ===")
    try:
        reading = fetch_latest_reading()
    except Exception as e:
        print(f"  ERROR: {e}")
        raise SystemExit(1)

    status = write_status(reading)
    append_log(status)

    print(f"  observed_at={status['observed_at']}  wbgt_c={status['wbgt_c']}  "
          f"risk_level={status['risk_level']}  ({status['data_type']})")
    print(f"  wrote {STATUS_PATH.name}, appended to {LOG_PATH.name}")

    if status["alert"]:
        print(f"\n  *** ALERT: {status['risk_level']} — WBGT {status['wbgt_c']}\u00b0C ***")
        try_desktop_notification(status)
    else:
        print("  no alert (below Severe Warning threshold)")

    print("\n=== Personalized classification examples (same reading, different profiles) ===")
    demo_profiles = [
        ("general adult, no conditions", {"age": 35}),
        ("70 years old", {"age": 70}),
        ("8 years old", {"age": 8}),
        ("adult with a chronic condition", {"age": 40, "has_chronic_condition": True}),
    ]
    for label, profile in demo_profiles:
        result = classify_for_profile(status["wbgt_c"], profile)
        flag = "ALERT" if result["alert"] else "ok"
        print(f"  [{flag:5s}] {label:<32s} measured={result['measured_risk_level']:<15s} "
              f"-> effective={result['effective_risk_level']}")