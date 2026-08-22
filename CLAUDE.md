# CLAUDE.md

Project context for coding agents. Keep this short — if it grows past
two screens, it stops being read.

## What this is

A heat-safety map for Tokyo, built for the 都知事杯オープンデータ・ハッカソン.
Submission is a recorded demo, judged partly on effective use of data
from the Tokyo Open Data Catalog.

**The one user story everything serves:**

> It's 2pm in August. I need to get from A to B. Tell me whether to go
> now, and which way to walk.

If a change doesn't serve that sentence, it isn't in scope. Ask before
adding features.

<!-- TODO: replace with the team's final wording if it changed -->

## Stack

- **Data pipeline:** Python (pandas, geopandas, shapely). Runs locally,
  not in production.
- **Frontend:** React + Vite. Static build.
- **Deploy:** Cloudflare Pages. Workers only if genuinely needed.
- **Storage:** R2 for raw files too large for Git.

## Repo layout

```
*.py                 pipeline scripts (repo root)
csv/                 raw source data — gitignored, fetched from R2
<GIS folders>/       raw GIS shapefiles — currently committed at root
cleaned_data/        intermediate outputs — gitignored, regenerable
outputs/             charts and figures for the pitch — committed
web/                 frontend
web/public/data/     small, clipped GeoJSON the app loads — committed
```

**Rule:** `cleaned_data/` is intermediate. Only small, web-ready files
go in `web/public/data/`, because that is what Pages serves. If a file
there exceeds a few MB, simplify the geometry rather than shipping it.

## Conventions

**Paths.** Never hardcode absolute paths. Anchor to the repo:

```python
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "csv"
```

Add `.parent` per directory level if the script moves into a subfolder.

**Raw data is never edited in place.** Scripts read from `csv/` and
write elsewhere. Anything generated must be reproducible by re-running
the script.

**Print counts at every stage.** Rows in, rows matched, rows dropped,
rows written. Silent data loss is the default failure mode here and
counts are how it gets caught.

**Cache external API responses to disk.** Overpass and the 環境省 WBGT
endpoint are free shared services. Query once, iterate on the cache.

**Commits:** Conventional Commits. `type(scope): subject`, imperative,
lowercase, no trailing period. Body explains *why*.

## Data sources

<!-- TODO: keep SOURCES.md authoritative; this is a summary -->

- **WBGT** — 環境省 熱中症予防情報サイト. Live feed, seasonal (roughly
  late April to late October). Historical CSV also available.
- **Cooling shelters** — 東京都 (wbgt.metro.tokyo.lg.jp). Addresses
  only, no coordinates — these must be geocoded.
- **Green / water / parks** — Tokyo Open Data Catalog. Polygons.
- **Ward boundaries** — 国土数値情報 N03. Used to validate geocoding.
- **Konbini** — OpenStreetMap via Overpass. ODbL, attribution required.
  Supplementary fallback layer, not a primary source.

## Constraints that are not negotiable

**Do not invent health thresholds.** WBGT tiers and their guidance come
from 環境省. The app displays official guidance; it does not compute a
personal risk verdict. Age and condition inputs change *what is shown*
and *when a break is suggested* — they never feed a made-up multiplier.

**Do not collect personal data.** No accounts, no stored age or health
information. User inputs live in session state only.

**Routing weights are a heuristic and must be labelled as such.** The
exposure penalty is our own invention, not science. Keep it visible and
adjustable rather than presenting it as authoritative.

**Do not do heavy computation at request time.** Spatial joins, edge
weighting, and coolness scoring happen offline and ship as static
files. Routing runs client-side or off precomputed weights.

## Before you start

- Read `SOURCES.md` for dataset provenance and licences.
- Check `.env.example` for required credentials. Never commit `.env`.
- Run `python fetch_raw.py --list` to see what's in R2 before assuming
  a file exists locally.
