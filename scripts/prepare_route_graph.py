"""Pre-score a cached OSMnx walking graph for fast API routing."""

from __future__ import annotations

import argparse
import os
import sys
import pickle
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
ROUTE_CACHE_DIR = ROOT_DIR / ".cache" / "cool_route"
os.environ.setdefault("MPLCONFIGDIR", str(ROUTE_CACHE_DIR / "matplotlib"))
sys.path.insert(0, str(ROOT_DIR))

import osmnx as ox
from pyproj import CRS

from Cool_Route import CACHE_DIR, score_graph_edges

# Changed output extension to .pkl
DEFAULT_OUTPUT = CACHE_DIR / "scored_walking.pkl"

def discover_input() -> Path:
    candidates = sorted(
        path for path in CACHE_DIR.glob("walk_*.graphml") if "scored" not in path.name
    )
    if not candidates:
        raise FileNotFoundError(
            "No cached walk_*.graphml exists. Run Cool_Route.py once to download one, "
            "or pass --input."
        )
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise RuntimeError(f"Multiple walking graphs found ({names}); pass --input explicitly.")
    return candidates[0]

def graph_bounds_wgs84(graph) -> tuple[float, float, float, float]:
    nodes = ox.convert.graph_to_gdfs(graph, nodes=True, edges=False)
    west, south, east, north = nodes.to_crs(4326).total_bounds
    return float(west), float(south), float(east), float(north)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add cooling scores to a cached OSMnx walking graph"
    )
    parser.add_argument("--input", type=Path, help="raw walking GraphML")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    input_path = args.input or discover_input()
    if not input_path.exists():
        raise FileNotFoundError(f"Walking graph not found: {input_path}")

    print(f"Loading walking graph: {input_path}")
    graph = ox.io.load_graphml(input_path)
    if not CRS.from_user_input(graph.graph["crs"]).is_projected:
        graph = ox.projection.project_graph(graph)

    print(f"Graph contains {len(graph):,} nodes and {graph.number_of_edges():,} edges")
    bounds = graph_bounds_wgs84(graph)
    graph = score_graph_edges(graph, bounds)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    # Save as high-performance binary pickle instead of XML graphml
    with open(args.output, "wb") as f:
        pickle.dump(graph, f, protocol=pickle.HIGHEST_PROTOCOL)
        
    print(f"Wrote pre-scored walking graph: {args.output}")

if __name__ == "__main__":
    main()