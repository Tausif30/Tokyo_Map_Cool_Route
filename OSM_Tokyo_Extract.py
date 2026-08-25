"""
============================================================================
Tokyo Open Data Hackathon 2026 — Heat Stroke Prevention Project
OSM_Tokyo_Extract.py — turns the Kanto PBF you already have into the
layers Cool_Route.py actually needs to route ANY start/end pair in Tokyo,
plus a few extra POI layers worth having as candidate "safe stop" points.

WHY THIS ISN'T "DOWNLOAD EVERYTHING AS ONE GEOJSON":
------------------------------------------------------------------------
Buildings are ~85-90% of "everything OSM knows about Tokyo" by data
volume, and they're the one layer Cool_Route.py's routing/scoring logic
doesn't use at all (no heat-exposure signal comes from a building
footprint itself). Measured on a real OSM extract, a *lean* building
GeoJSON feature (footprint + one "building" tag, no address/name/etc.)
already averages ~570 bytes. At a conservative estimate of ~3-4 million
building footprints across the wards + Tama, that alone is ~1.7-2.3 GB
before you've added a single road or POI. Keeping the full OSM tag set
(name, addr:*, building:levels, ...) roughly doubles that. A citywide
"everything" GeoJSON is realistically a 2-5 GB single file — something
no browser can parse, that geopandas will balloon further in RAM to
load, and that isn't spatially indexed, so you can't even query
"buildings near this point" without loading the whole thing first.

None of that is needed for what you're actually building. This script
instead writes THREE kinds of output, each in the format suited to its
job:

  1. Tokyo_Walk_Network.graphml — the pedestrian routing graph, as an
     osmnx-compatible networkx.MultiDiGraph. Point Cool_Route.py's
     `--graphml` flag at this file and it routes ANY start/end pair
     in the clipped area with zero live Overpass downloads (verified:
     this file loads via ox.io.load_graphml and works directly with
     ox.projection.project_graph / ox.convert.graph_to_gdfs /
     ox.distance.nearest_nodes / ox.routing.route_to_gdf — the exact
     calls acquire_graph()/score_graph_edges()/calculate_routes() in
     Cool_Route.py already use).
  2. Small POI GeoJSON layers (stations, station entrances, schools) —
     candidate additions to Nearby_Cool_Spots.py / Cool_Route.py's
     destination set. These are legitimately GeoJSON-appropriate:
     point data, tens of thousands of rows at most, no reason not to.
  3. Buildings.geojson — OFF by default. Pass --include-buildings if
     you want it anyway (e.g. for a visual basemap layer), but for
     rendering "the whole city looks like a map" in a Google-Maps-like
     frontend, vector tiles (e.g. tippecanoe/tilemaker -> PMTiles served
     straight from R2) are the standard tool for this, not a multi-GB
     GeoJSON the browser has to fetch and parse in one shot.

INPUT: osm_raw/kanto-latest.osm.pbf (the 460 MB file wrangler.py already
knows not to upload — you don't need to re-download anything from OSM).
Clipped to outputs/Tokyo_Ward_Boundaries.geojson if present, else a
rough Tokyo Metropolis bounding box (printed clearly when that fallback
is used, since a bbox will include slivers of Kawasaki/Saitama/Chiba at
the edges — harmless for routing continuity, just noted).

NOTE: Tokyo_Ward_Boundaries.geojson, per its name, may only cover the
23 special wards. If you need Tama-area routing too, pass a wider
--boundary file (e.g. the full Tokyo prefecture boundary).

USAGE:
    pip install pyrosm

    If you're extracting from a big regional PBF (Kanto is 460 MB+, 7
    prefectures) and this hangs with zero output for more than a few
    minutes, that's a known pyrosm failure mode on regional-sized files
    — run OSM_Crop_To_Tokyo.py first to shrink it to a Tokyo-only PBF,
    then point this script at that instead:
        python OSM_Crop_To_Tokyo.py
        python OSM_Tokyo_Extract.py --pbf outputs/Tokyo_Only.osm.pbf

    python OSM_Tokyo_Extract.py                     # network + POIs only
    python OSM_Tokyo_Extract.py --include-buildings  # + Buildings.geojson
    python OSM_Tokyo_Extract.py --network-type driving+service --no-simplify

Then point Cool_Route.py at the graph:
    python Cool_Route.py --start 35.69 139.70 --end 35.68 139.71 \
        --graphml outputs/Tokyo_Walk_Network.graphml
============================================================================
"""

import argparse
from pathlib import Path

import geopandas as gpd
import osmnx as ox
from pyrosm import OSM

BASE_DIR = Path(__file__).parent
DEFAULT_PBF = BASE_DIR / "osm_raw" / "kanto-latest.osm.pbf"
DEFAULT_BOUNDARY = BASE_DIR / "outputs" / "Tokyo_Ward_Boundaries.geojson"
OUT_DIR = BASE_DIR / "outputs"
OUT_DIR.mkdir(exist_ok=True)

# Rough Tokyo Metropolis bbox (west, south, east, north) — only used if
# no boundary file is found. Includes Tama; will also include some of
# the neighbouring prefectures at the edges.
FALLBACK_BBOX = (138.94, 35.50, 139.92, 35.90)

# Same simplestyle-spec convention Map_Value_Fix.py uses, so these
# layers preview consistently with the rest of the pipeline in
# geojson.io / QGIS / GitHub.
LAYER_COLORS = {
    "Railway Stations": "#e91e63",
    "Railway Station Entrances": "#f06292",
    "Kindergartens": "#ffca28",
    "Schools": "#ff5722",
    "Vocational Colleges": "#fb8c00",
    "Universities": "#d84315",
    "Research Institutes": "#6d4c41",
    "Buildings": "#9e9e9e",
    "Hospitals": "#4caf50",
    "Clinics": "#81c784",
    "Restaurants": "#ff9800",
    "Cafes": "#ffb74d",
    "Supermarkets": "#3f51b5",
    "Fast Food": "#ff7043",
    "Offices": "#607d8b",
    "Departmental Stores": "#795548",
}


def human(n_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


def load_boundary(boundary_path):
    """Return a single (Multi)Polygon to clip the PBF read to, or a bbox
    tuple if no boundary file is available."""
    if boundary_path and boundary_path.exists():
        gdf = gpd.read_file(boundary_path)
        try:
            geom = gdf.geometry.union_all()  # geopandas >= 1.0
        except AttributeError:
            geom = gdf.unary_union  # older geopandas
        print(f"  Clipping to {boundary_path.name} "
              f"({len(gdf)} ward polygon(s) merged)")
        return geom
    print(f"  WARNING: {boundary_path} not found — falling back to a "
          f"rough Tokyo Metropolis bbox {FALLBACK_BBOX}.")
    print("  This will include slivers of neighbouring prefectures at "
          "the edges. Pass --boundary for a precise clip.")
    return list(FALLBACK_BBOX)


def add_style(gdf, category):
    gdf = gdf.copy()
    gdf["category"] = category
    gdf["marker-color"] = LAYER_COLORS.get(category, "#999999")
    gdf["color_hex"] = LAYER_COLORS.get(category, "#999999")
    return gdf


def write_geojson(gdf, out_name, category):
    if gdf is None or len(gdf) == 0:
        print(f"  (no features found for {category} — skipping {out_name})")
        return
    gdf = add_style(gdf, category)
    # Drop the raw 'tags' dict column pyrosm keeps around — GeoJSON can't
    # serialize nested dicts cleanly and it's redundant with the
    # already-expanded tag columns.
    if "tags" in gdf.columns:
        gdf = gdf.drop(columns=["tags"])
    out_path = OUT_DIR / out_name
    gdf.to_file(out_path, driver="GeoJSON")
    size = out_path.stat().st_size
    print(f"  wrote {out_name}  ({len(gdf):,} features, {human(size)})")
    return size


# ---------------------------------------------------------------------
# 1. Routing graph — the piece that actually unlocks "route ANY two
#    points in Tokyo" for Cool_Route.py.
# ---------------------------------------------------------------------
def build_walk_network(osm, network_type, simplify):
    print(f"\n=== Building {network_type} routing graph ===")
    # 'oneway' is kept explicitly: pyrosm treats walking as bidirectional
    # regardless, but it matters for correctness if you ever build a
    # --network-type driving graph from this same script.
    nodes, edges = osm.get_network(
        network_type=network_type, nodes=True, tags_to_keep=["highway", "name", "oneway"]
    )
    print(f"  raw network: {len(nodes):,} nodes, {len(edges):,} edges")

    graph = osm.to_graph(
        nodes, edges,
        graph_type="networkx",
        osmnx_compatible=True,   # renames osmid/x/y so ox.* functions work
        simplify=simplify,       # collapse degree-2 shape nodes into edges
    )

    # osmnx's GraphML loader requires the 'oneway' edge attribute to be a
    # real Python bool (it round-trips to the literal string "True"/
    # "False" and rejects anything else on reload — raw OSM values like
    # "yes"/"no"/None crash ox.io.load_graphml()). Normalize here so the
    # file we write is actually loadable by Cool_Route.py's --graphml.
    ONEWAY_TRUE = {"yes", "1", "true", "-1", "reverse"}
    for _, _, data in graph.edges(data=True):
        data["oneway"] = str(data.get("oneway")).lower() in ONEWAY_TRUE

    if simplify:
        print(f"  after topological simplification: "
              f"{graph.number_of_nodes():,} nodes, "
              f"{graph.number_of_edges():,} edges")

    out_path = OUT_DIR / "Tokyo_Walk_Network.graphml"
    ox.io.save_graphml(graph, out_path)
    size = out_path.stat().st_size
    print(f"  wrote {out_path.name}  ({human(size)})")
    print(f"  -> use with: python Cool_Route.py ... --graphml {out_path}")
    return graph


def extract_kindergartens(osm):
    print("\n=== Extracting kindergartens/preschools ===")
    kindergartens = osm.get_pois(custom_filter={
        "amenity": ["kindergarten", "preschool", "childcare"],
    })
    return write_geojson(kindergartens, "Kindergartens.geojson", "Kindergartens")


def extract_schools(osm):
    print("\n=== Extracting schools (elementary/middle/high) ===")
    # amenity=school covers elementary + middle/junior-high + high school
    # together in Japan's own OSM tagging convention (JA:Tag:amenity=school
    # lists 小学校/中学校/高等学校/義務教育学校/中等教育学校 as all falling
    # under this one tag) — OSM has no separate amenity value per level.
    # education=school is a 2025-approved tag meant to eventually replace
    # amenity=school; both are queried since real data is mid-migration.
    # Where a mapper DID add isced:level or school=* (elementary/primary/
    # secondary), that value is kept in the output properties so you can
    # filter by level for the subset of schools that have it — but don't
    # expect that to cover most rows; it's optional per-mapper metadata,
    # not something OSM guarantees is filled in.
    schools = osm.get_pois(custom_filter={
        "amenity": ["school"],
        "education": ["school"],
    })
    return write_geojson(schools, "Schools.geojson", "Schools")


def extract_vocational_colleges(osm):
    print("\n=== Extracting vocational schools / colleges ===")
    # amenity=college = further/vocational education, NOT university —
    # this is also Japan's OSM convention for 専門学校/短期大学.
    colleges = osm.get_pois(custom_filter={"amenity": ["college"]})
    return write_geojson(colleges, "Vocational_Colleges.geojson", "Vocational Colleges")


def extract_research_institutes(osm):
    print("\n=== Extracting research institutes ===")
    institutes = osm.get_pois(custom_filter={
        "amenity": ["research_institute"],
        "office": ["research"],
    })
    return write_geojson(institutes, "Research_Institutes.geojson", "Research Institutes")


# ---------------------------------------------------------------------
# 2. POI layers — small, genuinely GeoJSON-appropriate additions to the
#    "places to route toward / stop at" set.
# ---------------------------------------------------------------------
def extract_stations(osm):
    print("\n=== Extracting railway stations ===")
    stations = osm.get_pois(custom_filter={
        "railway": ["station", "halt", "tram_stop"],
        "public_transport": ["station"],
    })
    return write_geojson(stations, "Railway_Stations.geojson", "Railway Stations")


def extract_station_entrances(osm):
    print("\n=== Extracting station entrances/exits ===")
    entrances = osm.get_pois(custom_filter={
        "railway": ["subway_entrance", "train_station_entrance"],
    })
    return write_geojson(
        entrances, "Railway_Station_Entrances.geojson", "Railway Station Entrances"
    )


def extract_universities(osm):
    print("\n=== Extracting universities ===")
    universities = osm.get_pois(custom_filter={"amenity": ["university"]})
    return write_geojson(universities, "Universities.geojson", "Universities")



def extract_hospitals(osm):
    print("\n=== Extracting hospitals ===")
    hospitals = osm.get_pois(custom_filter={"amenity": ["hospital"]})
    return write_geojson(hospitals, "Hospitals.geojson", "Hospitals")


def extract_clinics(osm):
    print("\n=== Extracting clinics ===")
    clinics = osm.get_pois(custom_filter={"amenity": ["clinic"]})
    return write_geojson(clinics, "Clinics.geojson", "Clinics")


def extract_restaurants(osm):
    print("\n=== Extracting restaurants ===")
    restaurants = osm.get_pois(custom_filter={"amenity": ["restaurant"]})
    return write_geojson(restaurants, "Restaurants.geojson", "Restaurants")


def extract_cafes(osm):
    print("\n=== Extracting cafes ===")
    cafes = osm.get_pois(custom_filter={"amenity": ["cafe"]})
    return write_geojson(cafes, "Cafes.geojson", "Cafes")


def extract_supermarkets(osm):
    print("\n=== Extracting supermarkets ===")
    supermarkets = osm.get_pois(custom_filter={"shop": ["supermarket"]})
    return write_geojson(supermarkets, "Supermarkets.geojson", "Supermarkets")


def extract_fast_food(osm):
    print("\n=== Extracting fast food ===")
    fast_food = osm.get_pois(custom_filter={"amenity": ["fast_food"]})
    return write_geojson(fast_food, "Fast_Food.geojson", "Fast Food")

def extract_departmental_stores(osm):
    print("\n=== Extracting departmental stores ===")
    departmental_stores = osm.get_pois(custom_filter={"shop": ["depart*"]})
    return write_geojson(departmental_stores, "Departmental_Stores.geojson", "Departmental Stores")

def extract_offices(osm):
    print("\n=== Extracting offices ===")
    offices = osm.get_pois(custom_filter={"office": True})
    return write_geojson(offices, "Offices.geojson", "Offices")


# ---------------------------------------------------------------------
# 3. Buildings — opt-in only. See module docstring for why.
# ---------------------------------------------------------------------
def extract_buildings(osm):
    print("\n=== Extracting buildings (--include-buildings was set) ===")
    buildings = osm.get_buildings(tags_to_keep=["building"])
    keep_cols = [c for c in ["id", "building", "geometry"] if c in buildings.columns]
    buildings = buildings[keep_cols]
    return write_geojson(buildings, "Buildings.geojson", "Buildings")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, default=DEFAULT_PBF,
                         help=f"Path to source PBF (default: {DEFAULT_PBF})")
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY,
                         help="Polygon GeoJSON to clip to "
                              f"(default: {DEFAULT_BOUNDARY})")
    parser.add_argument("--network-type", default="walking",
                         choices=["walking", "driving", "driving+service", "cycling", "all"],
                         help="OSM network type for the routing graph (default: walking)")
    parser.add_argument("--no-simplify", action="store_true",
                         help="Skip topological simplification of the graph "
                              "(keeps every shape-point as a graph node — much bigger)")
    parser.add_argument("--include-buildings", action="store_true",
                         help="Also write Buildings.geojson. Read the module "
                              "docstring first — this is the multi-GB one.")
    args = parser.parse_args()

    if not args.pbf.exists():
        raise FileNotFoundError(
            f"{args.pbf} not found. This script reads the Kanto PBF you "
            "already downloaded via fetch_raw.py, it doesn't fetch OSM data "
            "itself. Pass --pbf if it's somewhere else."
        )

    print(f"=== Loading {args.pbf.name} ({human(args.pbf.stat().st_size)}) ===")
    boundary = load_boundary(args.boundary)
    osm = OSM(str(args.pbf), bounding_box=boundary)

    written_bytes = 0
    build_walk_network(osm, args.network_type, simplify=not args.no_simplify)
    written_bytes += extract_stations(osm) or 0
    written_bytes += extract_station_entrances(osm) or 0
    written_bytes += extract_kindergartens(osm) or 0
    written_bytes += extract_schools(osm) or 0
    written_bytes += extract_vocational_colleges(osm) or 0
    written_bytes += extract_universities(osm) or 0
    written_bytes += extract_research_institutes(osm) or 0
    written_bytes += extract_hospitals(osm) or 0
    written_bytes += extract_clinics(osm) or 0
    written_bytes += extract_restaurants(osm) or 0
    written_bytes += extract_cafes(osm) or 0
    written_bytes += extract_supermarkets(osm) or 0
    written_bytes += extract_fast_food(osm) or 0
    written_bytes += extract_offices(osm) or 0
    written_bytes += extract_departmental_stores(osm) or 0
    if args.include_buildings:
        written_bytes += extract_buildings(osm) or 0
    else:
        print("\n(Skipping buildings — pass --include-buildings to write "
              "Buildings.geojson too. Expect it to be by far the biggest "
              "file this script can produce; see the module docstring.)")

    print(f"\n=== Done. GeoJSON layers total: {human(written_bytes)} "
          f"(routing graph reported separately above) ===")
    print(f"All files written to {OUT_DIR}")