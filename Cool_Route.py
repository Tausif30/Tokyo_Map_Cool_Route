"""Calculate shortest, coolest, and balanced walking routes through Tokyo.

The pedestrian network comes from OpenStreetMap through OSMnx. The local
GeoJSON files in ``outputs/`` do not define connected streets; instead, they
are spatially joined to the OSM street edges to estimate shade and cooling.

Example:
    python Cool_Route.py \
        --start 35.6909 139.7003 \
        --end 35.6852 139.7100 \
        --wbgt 31

Coordinates are always given as LATITUDE LONGITUDE. The output is a GeoJSON
containing three route alternatives plus start/end markers.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache" / "cool_route"
# OSMnx imports Matplotlib. Keep its cache inside this project so the script
# also works in restricted/container environments without a writable home.
os.environ.setdefault("MPLCONFIGDIR", str(CACHE_DIR / "matplotlib"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from pyproj import CRS
from shapely.geometry import Point


OUTPUT_DIR = BASE_DIR / "outputs"
DEFAULT_OUTPUT = OUTPUT_DIR / "Cool_Routes.geojson"

# The weights sum to 1. A missing layer contributes zero rather than silently
# making the remaining layers more influential.
COOLING_LAYERS = {
    "park_score": ("Parks_Green_Spaces.geojson", 25.0, 0.22),
    "protected_green_score": ("Protected_Green_Spaces.geojson", 20.0, 0.08),
    "housing_green_score": ("Public_Housing_Greenery.geojson", 15.0, 0.05),
    "facility_green_score": ("Public_Facility_Greenery.geojson", 15.0, 0.05),
    "water_score": ("Water_Canals.geojson", 40.0, 0.05),
    "station_score": ("Drinking_Station.geojson", 100.0, 0.10),
}
TREE_WEIGHT = 0.45

ROUTE_COLORS = {
    "shortest": "#d1495b",
    "coolest": "#2e7d32",
    "balanced": "#1976d2",
}


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Return straight-line distance in metres between (lat, lon) pairs."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + (
        math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6_371_009 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def query_bounds(
    center: tuple[float, float], radius_m: float
) -> tuple[float, float, float, float]:
    """Return a conservative WGS84 (west, south, east, north) query box."""
    lat, lon = center
    lat_pad = radius_m / 110_574
    lon_scale = max(111_320 * math.cos(math.radians(lat)), 1)
    lon_pad = radius_m / lon_scale
    return lon - lon_pad, lat - lat_pad, lon + lon_pad, lat + lat_pad


def graph_cache_path(
    start: tuple[float, float], end: tuple[float, float], padding_m: float
) -> Path:
    value = ",".join(f"{v:.5f}" for v in (*start, *end, padding_m))
    digest = hashlib.sha256(value.encode()).hexdigest()[:16]
    return CACHE_DIR / f"walk_{digest}.graphml"


def acquire_graph(
    start: tuple[float, float],
    end: tuple[float, float],
    padding_m: float,
    use_cache: bool = True,
    graphml: Path | None = None,
) -> tuple[nx.MultiDiGraph, tuple[float, float, float, float]]:
    """Load or download a walking graph that contains both endpoints."""
    center = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    radius_m = haversine_m(start, end) / 2 + padding_m
    bounds = query_bounds(center, radius_m)

    cache_path = graphml or graph_cache_path(start, end, padding_m)
    if cache_path.exists():
        print(f"Loading cached walking graph: {cache_path}")
        graph = ox.io.load_graphml(cache_path)
    else:
        if graphml is not None:
            raise FileNotFoundError(f"GraphML file not found: {graphml}")
        print(
            "Downloading OpenStreetMap walking graph "
            f"(radius {radius_m / 1000:.1f} km)..."
        )
        ox.settings.use_cache = True
        ox.settings.cache_folder = CACHE_DIR / "osmnx"
        ox.settings.requests_timeout = 180
        graph = ox.graph.graph_from_point(
            center,
            dist=radius_m,
            dist_type="bbox",
            network_type="walk",
            simplify=True,
            retain_all=False,
        )

    graph_crs = CRS.from_user_input(graph.graph["crs"])
    if not graph_crs.is_projected:
        graph = ox.projection.project_graph(graph)

    if use_cache and graphml is None and not cache_path.exists():
        ox.io.save_graphml(graph, cache_path)
        print(f"Cached walking graph: {cache_path}")

    return graph, bounds


def read_layer(
    path: Path,
    bounds: tuple[float, float, float, float],
    target_crs: CRS,
) -> gpd.GeoDataFrame:
    """Read only features around the route and project them to metres."""
    if not path.exists():
        print(f"  Missing optional layer: {path.name}")
        return gpd.GeoDataFrame(geometry=[], crs=target_crs)

    try:
        layer = gpd.read_file(path, bbox=bounds, columns=[])
    except TypeError:
        # Compatibility fallback for engines that do not accept columns=[].
        layer = gpd.read_file(path, bbox=bounds)[["geometry"]]

    if layer.empty:
        print(f"  {path.name}: no nearby features")
        return gpd.GeoDataFrame(geometry=[], crs=target_crs)

    layer = layer[layer.geometry.notna() & ~layer.geometry.is_empty].copy()
    if layer.crs is None:
        raise ValueError(f"{path.name} has no CRS")
    layer = layer.to_crs(target_crs)
    layer.geometry = layer.geometry.make_valid()
    print(f"  {path.name}: {len(layer):,} nearby features")
    return layer[["geometry"]]


def proximity_fraction(
    edges: gpd.GeoDataFrame,
    layer: gpd.GeoDataFrame,
    distance_m: float,
) -> pd.Series:
    """Cooling-proximity score per edge: 1.0 if an edge touches a feature
    in `layer`, decaying to 0.0 at distance_m away or farther.

    REWRITTEN FOR CITYWIDE SCALE. The previous version buffered every
    feature in a layer (e.g. every park polygon in Tokyo), spatial-joined
    to find edges near ANY buffered feature, then called `.union_all()`
    on all the matched buffers before measuring exact overlap length.
    That narrowing step helps in one district, where "features near some
    edge" is a small slice of the layer. At full-Tokyo scale it barely
    narrows anything: a dense citywide walking network sits near almost
    every park in the city, so the "matched" set is nearly the WHOLE
    layer, and `.union_all()` over thousands of overlapping, detailed
    park polygons is exactly what was hanging.

    This version never builds a citywide union at all. `sjoin_nearest`
    uses the same R-tree spatial index, but only asks "what's the single
    closest feature to this edge, and how far away is it?" instead of
    "build one shape covering every nearby feature, then measure exact
    overlap against it." That scales the same way whether the layer has
    50 features or 50,000 — there's no step whose cost depends on how
    MANY features are near the network as a whole.

    Trade-off worth knowing about: the old metric was "% of this edge's
    length that falls inside a buffer polygon." This one is "how close
    is the edge's nearest approach to a feature," linearly scored to 0
    at distance_m. Slightly different number, same intent (edges right
    next to a park score high, edges far from any park score low) — and
    it's arguably a fairer proxy for edges that just clip the corner of
    a buffer versus edges that run right alongside one.
    """
    zeros = pd.Series(0.0, index=edges.index, dtype=float)
    if layer.empty:
        return zeros

    nearest = gpd.sjoin_nearest(
        edges[["geometry"]],
        layer[["geometry"]],
        how="inner",
        max_distance=distance_m,
        distance_col="_dist_m",
    )
    # A handful of edges can tie for "closest feature" with more than one
    # candidate — keep only the closest match per edge.
    closest = nearest.groupby(nearest.index)["_dist_m"].min()
    closest = closest.reindex(edges.index)  # edges with nothing nearby -> NaN

    score = 1.0 - (closest / distance_m)
    return score.clip(lower=0.0, upper=1.0).fillna(0.0)


def tree_scores(
    edges: gpd.GeoDataFrame,
    trees: gpd.GeoDataFrame,
    buffer_m: float = 12.0,
) -> tuple[pd.Series, pd.Series]:
    """Return normalized shade proxy and raw nearby tree counts per edge.

    REWRITTEN FOR CITYWIDE SCALE. The previous version buffered every
    edge in the graph — hundreds of thousands of them, citywide — into
    its own 12 m-wide polygon before joining against tree points. That's
    a lot of geometry construction before the join even starts, and it
    scales with graph size, not with how many trees exist.

    `sjoin_nearest` with `max_distance` asks the R-tree "which edge is
    closest to this tree, and is it within buffer_m?" directly, with no
    per-edge buffer polygons at all. One side effect: a tree now counts
    toward its single nearest edge rather than every edge within 12 m —
    slightly different from before, and arguably more correct (a tree
    between two parallel streets shouldn't shade both equally), but
    worth knowing it's not byte-identical to the old numbers.
    """
    if trees.empty:
        zeros = pd.Series(0.0, index=edges.index, dtype=float)
        return zeros, zeros.astype(int)

    joined = gpd.sjoin_nearest(
        trees[["geometry"]],
        edges[["edge_id", "geometry"]],
        how="inner",
        max_distance=buffer_m,
    )
    counts = joined.groupby("edge_id").size().reindex(edges.index, fill_value=0)
    # Six trees per 100 m is treated as a strong tree-lined segment. This is
    # a tunable proxy, not a claim that every tree casts equal shade.
    trees_per_100m = counts / edges["length_m"].clip(lower=1.0) * 100
    score = (trees_per_100m / 6.0).clip(lower=0.0, upper=1.0)
    return score.astype(float), counts.astype(int)


def score_graph_edges(
    graph: nx.MultiDiGraph,
    bounds: tuple[float, float, float, float],
    layer_dir: Path = OUTPUT_DIR,
) -> nx.MultiDiGraph:
    """Attach environmental scores in [0, 1] to every graph edge."""
    print("Scoring streets with local cooling data...")
    _, indexed_edges = ox.convert.graph_to_gdfs(graph)
    edges = indexed_edges.reset_index()
    edges["edge_id"] = edges.index
    edges["length_m"] = pd.to_numeric(edges.get("length"), errors="coerce")
    edges["length_m"] = edges["length_m"].fillna(edges.geometry.length).clip(lower=0.1)
    target_crs = CRS.from_user_input(edges.crs)
    print(f"  {len(edges):,} edges to score")

    # Each step below prints how long it took. At citywide scale this can
    # legitimately take a while even after the union-free rewrite below —
    # these prints exist so a slow step still LOOKS like it's making
    # progress instead of looking exactly like a freeze.
    t0 = time.perf_counter()
    trees = read_layer(layer_dir / "Street_Trees.geojson", bounds, target_crs)
    edges["tree_score"], edges["nearby_tree_count"] = tree_scores(edges, trees)
    print(f"  tree_score: {time.perf_counter() - t0:.1f}s")

    weighted_columns: list[tuple[str, float]] = [("tree_score", TREE_WEIGHT)]
    for score_name, (filename, buffer_m, weight) in COOLING_LAYERS.items():
        t0 = time.perf_counter()
        layer = read_layer(layer_dir / filename, bounds, target_crs)
        edges[score_name] = proximity_fraction(edges, layer, buffer_m)
        print(f"  {score_name}: {time.perf_counter() - t0:.1f}s")
        weighted_columns.append((score_name, weight))

    edges["cooling_score"] = sum(edges[column] * weight for column, weight in weighted_columns)
    edges["cooling_score"] = edges["cooling_score"].clip(lower=0.0, upper=1.0)
    edges["heat_exposure"] = 1.0 - edges["cooling_score"]

    attributes = [
        "length_m",
        "nearby_tree_count",
        "tree_score",
        *COOLING_LAYERS.keys(),
        "cooling_score",
        "heat_exposure",
    ]
    for row in edges[["u", "v", "key", *attributes]].itertuples(index=False):
        data = graph.edges[row.u, row.v, row.key]
        for attribute in attributes:
            data[attribute] = getattr(row, attribute)

    return graph


def wbgt_multiplier(wbgt_c: float) -> float:
    """Increase the route's cooling preference as WBGT risk rises."""
    if wbgt_c < 21:
        return 0.10
    if wbgt_c < 25:
        return 0.25
    if wbgt_c < 28:
        return 0.50
    if wbgt_c < 31:
        return 0.75
    return 1.00


def nearest_graph_nodes(
    graph: nx.MultiDiGraph,
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[int, int]:
    """Project input coordinates and snap them to graph nodes."""
    node_ids, distances = snap_graph_nodes(graph, start, end)
    if max(distances) > 300:
        print(
            "WARNING: an endpoint snapped more than 300 m to the walking "
            f"network (start={distances[0]:.0f} m, end={distances[1]:.0f} m)."
        )
    return node_ids


def snap_graph_nodes(
    graph: nx.MultiDiGraph,
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[tuple[int, int], tuple[float, float]]:
    """Return endpoint node IDs and their snap distances in metres."""
    points = gpd.GeoSeries(
        [Point(start[1], start[0]), Point(end[1], end[0])],
        crs="EPSG:4326",
    ).to_crs(graph.graph["crs"])
    node_ids, distances = ox.distance.nearest_nodes(
        graph,
        X=points.x.to_numpy(),
        Y=points.y.to_numpy(),
        return_dist=True,
    )
    return (
        (int(node_ids[0]), int(node_ids[1])),
        (float(distances[0]), float(distances[1])),
    )


def route_frame(
    graph: nx.MultiDiGraph, route: list[int], weight: str
) -> gpd.GeoDataFrame:
    return ox.routing.route_to_gdf(graph, route, weight=weight)


def summarize_route(frame: gpd.GeoDataFrame) -> dict[str, float]:
    length = float(frame["length_m"].sum())

    def weighted_average(column: str) -> float:
        if length <= 0:
            return 0.0
        return float((frame[column] * frame["length_m"]).sum() / length)

    return {
        "length_m": length,
        "walking_minutes": length / 80.0,
        "heat_exposure_index": weighted_average("heat_exposure"),
        "cooling_score": weighted_average("cooling_score"),
        "tree_score": weighted_average("tree_score"),
        "park_score": weighted_average("park_score"),
        "station_score": weighted_average("station_score"),
    }


def calculate_routes(
    graph: nx.MultiDiGraph,
    origin: int,
    destination: int,
    wbgt_c: float,
    max_detour_pct: float,
) -> dict[str, dict]:
    """Calculate the three route alternatives and their summaries dynamically."""
    try:
        shortest_nodes = nx.shortest_path(graph, origin, destination, weight="length_m")
    except nx.NetworkXNoPath as exc:
        raise RuntimeError("No walking path connects the selected endpoints") from exc

    shortest_frame = route_frame(graph, shortest_nodes, "length_m")
    shortest_summary = summarize_route(shortest_frame)
    shortest_distance = shortest_summary["length_m"]

    # Dynamic Weight: Prevents mutating the entire graph. Handles parallel edges.
    def coolest_weight(u, v, edge_dict):
        return min(
            attr["length_m"] * (0.10 + attr.get("heat_exposure", 0.0))
            for attr in edge_dict.values()
        )

    coolest_nodes = nx.shortest_path(graph, origin, destination, weight=coolest_weight)
    coolest_frame = route_frame(graph, coolest_nodes, "length_m")

    risk = wbgt_multiplier(wbgt_c)
    candidates: list[tuple[gpd.GeoDataFrame, dict[str, float]]] = [
        (shortest_frame, shortest_summary)
    ]
    seen = {tuple(shortest_nodes)}
    
    for alpha in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0):
        def balanced_weight(u, v, edge_dict, a=alpha):
            return min(
                attr["length_m"] * (1.0 + a * risk * attr.get("heat_exposure", 0.0))
                for attr in edge_dict.values()
            )

        nodes = nx.shortest_path(graph, origin, destination, weight=balanced_weight)
        key = tuple(nodes)
        if key in seen:
            continue
        seen.add(key)
        
        frame = route_frame(graph, nodes, "length_m")
        candidates.append((frame, summarize_route(frame)))

    limit = shortest_distance * (1 + max_detour_pct / 100.0)
    eligible = [c for c in candidates if c[1]["length_m"] <= limit]
    
    balanced_frame, _ = min(
        eligible,
        key=lambda c: (c[1]["heat_exposure_index"], c[1]["length_m"]),
    )

    result = {
        "shortest": {"frame": shortest_frame},
        "coolest": {"frame": coolest_frame},
        "balanced": {"frame": balanced_frame},
    }
    
    for route_type, route in result.items():
        route["summary"] = summarize_route(route["frame"])
        route["summary"]["detour_pct"] = (
            route["summary"]["length_m"] / shortest_distance - 1
        ) * 100
        
    return result


def serialize_routes(routes: dict[str, dict]) -> list[dict]:
    """Convert route frames and summaries into JSON-safe API objects.

    ``coords`` is a list of line segments. Each coordinate is ``[lat, lon]``
    so it can be passed directly to Leaflet without another conversion.
    """
    labels = {
        "shortest": "Fastest",
        "coolest": "Coolest",
        "balanced": "Recommended",
    }
    descriptions = {
        "shortest": "Minimum walking distance",
        "coolest": "Minimum estimated heat exposure",
        "balanced": "Lowest exposure within the detour limit",
    }
    serialized = []

    for route_type in ("shortest", "coolest", "balanced"):
        route = routes[route_type]
        frame = route["frame"].to_crs(4326)
        segments: list[list[list[float]]] = []
        for geometry in frame.geometry:
            geometries = geometry.geoms if hasattr(geometry, "geoms") else [geometry]
            for line in geometries:
                if line.geom_type != "LineString":
                    continue
                segments.append(
                    [[round(lat, 7), round(lon, 7)] for lon, lat in line.coords]
                )

        summary = route["summary"]
        serialized.append(
            {
                "id": route_type,
                "label": labels[route_type],
                "description": descriptions[route_type],
                "distance_m": round(summary["length_m"]),
                "walking_minutes": round(summary["walking_minutes"], 1),
                "detour_pct": round(summary["detour_pct"], 1),
                "heat_exposure_index": round(summary["heat_exposure_index"], 3),
                "cooling_score": round(summary["cooling_score"], 3),
                "coords": segments,
            }
        )
    return serialized


def export_routes(
    routes: dict[str, dict],
    graph_crs: CRS | str,
    start: tuple[float, float],
    end: tuple[float, float],
    wbgt_c: float,
    output_path: Path,
) -> None:
    """Write route alternatives and endpoint markers to one WGS84 GeoJSON."""
    rows: list[dict] = []
    for route_type in ("shortest", "coolest", "balanced"):
        route = routes[route_type]
        geometry = route["frame"].geometry.union_all()
        summary = route["summary"]
        rows.append(
            {
                "route_type": route_type,
                "description": {
                    "shortest": "Minimum walking distance",
                    "coolest": "Minimum estimated heat exposure",
                    "balanced": "Lowest exposure within the detour limit",
                }[route_type],
                **{key: round(value, 3) for key, value in summary.items()},
                "wbgt_c": wbgt_c,
                "stroke": ROUTE_COLORS[route_type],
                "stroke-width": 6 if route_type == "balanced" else 4,
                "stroke-opacity": 0.85,
                "geometry": geometry,
            }
        )

    route_gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=graph_crs).to_crs(4326)
    endpoints = gpd.GeoDataFrame(
        [
            {
                "route_type": "start",
                "description": "Point A",
                "marker-color": "#2e7d32",
                "geometry": Point(start[1], start[0]),
            },
            {
                "route_type": "end",
                "description": "Point B",
                "marker-color": "#d1495b",
                "geometry": Point(end[1], end[0]),
            },
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )
    output = gpd.GeoDataFrame(
        pd.concat([route_gdf, endpoints], ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_file(output_path, driver="GeoJSON")


def print_summary(routes: dict[str, dict], output_path: Path) -> None:
    print("\nRoute comparison")
    print("-" * 78)
    print(
        f"{'Route':<11} {'Distance':>10} {'Walk':>9} "
        f"{'Detour':>9} {'Exposure':>10} {'Trees':>8} {'Parks':>8}"
    )
    for route_type in ("shortest", "coolest", "balanced"):
        values = routes[route_type]["summary"]
        print(
            f"{route_type.title():<11} "
            f"{values['length_m']:>8.0f} m "
            f"{values['walking_minutes']:>7.1f} m "
            f"{values['detour_pct']:>8.1f}% "
            f"{values['heat_exposure_index']:>10.3f} "
            f"{values['tree_score']:>8.3f} "
            f"{values['park_score']:>8.3f}"
        )
    print(f"\nWrote: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find shortest, coolest, and balanced walking routes in Tokyo."
    )
    parser.add_argument(
        "--start",
        nargs=2,
        required=True,
        type=float,
        metavar=("LAT", "LON"),
        help="Point A as latitude longitude",
    )
    parser.add_argument(
        "--end",
        nargs=2,
        required=True,
        type=float,
        metavar=("LAT", "LON"),
        help="Point B as latitude longitude",
    )
    parser.add_argument(
        "--wbgt",
        type=float,
        default=28.0,
        help="Current/forecast WBGT in Celsius (default: 28)",
    )
    parser.add_argument(
        "--max-detour-pct",
        type=float,
        default=15.0,
        help="Maximum balanced-route distance above shortest, in percent (default: 15)",
    )
    parser.add_argument(
        "--padding-m",
        type=float,
        default=1_000.0,
        help="Extra walking-network area around A/B in metres (default: 1000)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output GeoJSON path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--graphml",
        type=Path,
        help="Use an existing OSMnx GraphML instead of downloading a graph",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not save a newly downloaded graph",
    )
    args = parser.parse_args()
    if args.max_detour_pct < 0:
        parser.error("--max-detour-pct must be non-negative")
    if args.padding_m <= 0:
        parser.error("--padding-m must be positive")
    if not -90 <= args.start[0] <= 90 or not -90 <= args.end[0] <= 90:
        parser.error("latitude must be between -90 and 90")
    if not -180 <= args.start[1] <= 180 or not -180 <= args.end[1] <= 180:
        parser.error("longitude must be between -180 and 180")
    return args


def main() -> None:
    args = parse_args()
    start = tuple(args.start)
    end = tuple(args.end)

    direct_distance = haversine_m(start, end)
    print(f"A to B straight-line distance: {direct_distance / 1000:.2f} km")
    if direct_distance > 20_000 and args.graphml is None:
        print(
            "WARNING: this is a large live OpenStreetMap request. For repeated "
            "citywide routing, pre-download a Tokyo GraphML file."
        )

    graph, bounds = acquire_graph(
        start,
        end,
        padding_m=args.padding_m,
        use_cache=not args.no_cache,
        graphml=args.graphml,
    )
    graph = score_graph_edges(graph, bounds)
    origin, destination = nearest_graph_nodes(graph, start, end)
    routes = calculate_routes(
        graph,
        origin,
        destination,
        wbgt_c=args.wbgt,
        max_detour_pct=args.max_detour_pct,
    )
    export_routes(routes, graph.graph["crs"], start, end, args.wbgt, args.output)
    print_summary(routes, args.output)


if __name__ == "__main__":
    main()