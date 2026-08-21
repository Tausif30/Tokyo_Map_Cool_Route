"""
Downloads the actual polygon boundary of each
of Tokyo's 23 special wards.

SOURCE: MLIT's 国土数値情報 (National Land Numerical Information) "行政区域
データ" (N03, administrative boundaries) — as republished by NII's Geoshape
project in clean per-municipality GeoJSON.

OUTPUT:
    outputs/Tokyo_Ward_Boundaries.geojson - 23 ward polygons
"""

import json
import time
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR / "outputs"
OUT_DIR.mkdir(exist_ok=True)

GEOSHAPE_URL = "https://geoshape.ex.nii.ac.jp/city/geojson/latest/{code}.geojson"

# Tokyo's 23 special wards. Code order follows the Cabinet Office's
# official numbering (the "の"-shaped spiral radiating out from Chiyoda).
WARD_CODES = {
    "13101": "Chiyoda-ku", "13102": "Chuo-ku", "13103": "Minato-ku",
    "13104": "Shinjuku-ku", "13105": "Bunkyo-ku", "13106": "Taito-ku",
    "13107": "Sumida-ku", "13108": "Koto-ku", "13109": "Shinagawa-ku",
    "13110": "Meguro-ku", "13111": "Ota-ku", "13112": "Setagaya-ku",
    "13113": "Shibuya-ku", "13114": "Nakano-ku", "13115": "Suginami-ku",
    "13116": "Toshima-ku", "13117": "Kita-ku", "13118": "Arakawa-ku",
    "13119": "Itabashi-ku", "13120": "Nerima-ku", "13121": "Adachi-ku",
    "13122": "Katsushika-ku", "13123": "Edogawa-ku",
}


def fetch_ward(code, retries=3):
    url = GEOSHAPE_URL.format(code=code)
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"    attempt {attempt} failed for {code}: {e}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"Could not fetch ward {code} after {retries} attempts")


if __name__ == "__main__":
    print("=== Fetching Tokyo's 23 special ward boundaries ===")
    features = []
    
    for code, district_en in WARD_CODES.items():
        print(f"  {code} ({district_en}) ...")
        data = fetch_ward(code)
        
        for feat in data["features"]:
            props = feat["properties"]
            feat["properties"] = {
                "code": code,
                "district_en": district_en,
                "district_jp": props.get("N03_004"),
                "prefecture_jp": props.get("N03_001"),
            }
            features.append(feat)
            
        time.sleep(0.5)  # be polite to a free public research service

    boundaries = {"type": "FeatureCollection", "features": features}
    boundaries_path = OUT_DIR / "Tokyo_Ward_Boundaries.geojson"
    
    with open(boundaries_path, "w", encoding="utf-8") as f:
        json.dump(boundaries, f, ensure_ascii=False)
        
    print(f"\nWrote {boundaries_path}  ({len(features)} ward polygons)")