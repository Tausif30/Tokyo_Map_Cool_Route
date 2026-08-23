#!/usr/bin/env bash
# Runs on Railway at startup. Fetches outputs/ from R2 so the API has the
# GeoJSON files it needs, then hands off to uvicorn.
# R2 credentials and VITE_API_BASE_URL are set as env vars in Railway dashboard.
set -e

echo "=== Fetching outputs/ from R2 ==="
python fetch_raw.py --prefix outputs/

echo "=== Initial WBGT poll ==="
python WBGT_Monitor.py

echo "=== Starting WBGT background poller (every 30 min) ==="
(while true; do sleep 1800; python WBGT_Monitor.py; done) &

echo "=== Starting API ==="
exec uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}"
