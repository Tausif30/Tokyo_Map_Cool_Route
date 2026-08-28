import asyncio
import json
import os
import pickle
import numpy as np
from scipy.spatial import cKDTree
import geopandas as gpd
from shapely.geometry import Point
from contextlib import asynccontextmanager, suppress
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from Search_Places import build_index, search_places

from WBGT_Monitor import (
    STATUS_PATH as WBGT_STATUS_PATH,
    append_log as append_wbgt_log,
    classify_for_profile,
    fetch_latest_reading,
    write_status as write_wbgt_status,
)
from Nearby_Cool_Spots import nearby_cool_spots
from Cool_Route import (
    CACHE_DIR as ROUTE_CACHE_DIR,
    calculate_routes,
    haversine_m,
    serialize_routes,
)

WBGT_POLL_SECONDS = max(60, int(os.getenv("WBGT_POLL_SECONDS", "900")))

def _refresh_wbgt_status():
    status = write_wbgt_status(fetch_latest_reading())
    append_wbgt_log(status)
    return status

async def _wbgt_poll_loop():
    while True:
        try:
            status = await asyncio.to_thread(_refresh_wbgt_status)
            print(
                "WBGT refreshed: "
                f"{status['observed_at']} JST, {status['wbgt_c']} C"
            )
        except Exception as exc:
            print(f"WARNING: WBGT refresh failed: {exc}")
        await asyncio.sleep(WBGT_POLL_SECONDS)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    wbgt_task = asyncio.create_task(_wbgt_poll_loop())
    try:
        yield
    finally:
        wbgt_task.cancel()
        with suppress(asyncio.CancelledError):
            await wbgt_task

app = FastAPI(
    title="Tokyo Heat Stroke Prevention API",
    version="0.1",
    lifespan=lifespan,
)

PLACE_INDEX = build_index()

# Note the change to .pkl
DEPLOYED_ROUTE_GRAPH_PATH = Path(__file__).resolve().parent / "outputs" / "scored_walking.pkl"
LOCAL_ROUTE_GRAPH_PATH = ROUTE_CACHE_DIR / "scored_walking.pkl"
ROUTE_GRAPH_PATH = Path(
    os.getenv(
        "COOL_ROUTE_GRAPH",
        DEPLOYED_ROUTE_GRAPH_PATH if DEPLOYED_ROUTE_GRAPH_PATH.exists() else LOCAL_ROUTE_GRAPH_PATH,
    )
)

MAX_ROUTE_DISTANCE_M = 10_000
MAX_SNAP_DISTANCE_M = 300

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

def _load_wbgt_status():
    if not WBGT_STATUS_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail="No WBGT reading yet. Run WBGT_Monitor.py at least once first.",
        )
    with open(WBGT_STATUS_PATH, encoding="utf-8") as f:
        return json.load(f)

def _profile_from_query(age, is_pregnant, has_chronic_condition):
    return {"age": age, "is_pregnant": is_pregnant, "has_chronic_condition": has_chronic_condition}

# Load graph AND build KD-Tree exactly once
@lru_cache(maxsize=1)
def _load_route_data(path: str):
    graph_path = Path(path)
    if not graph_path.exists():
        raise FileNotFoundError(
            f"Prepared route graph is missing at {path}. Run preparation script first."
        )
    
    with open(graph_path, "rb") as f:
        graph = pickle.load(f)
        
    nodes = list(graph.nodes(data=True))
    node_ids = np.array([n[0] for n in nodes])
    coords = np.array([[n[1]["x"], n[1]["y"]] for n in nodes])
    tree = cKDTree(coords)
    
    return graph, node_ids, tree

@app.get("/wbgt/status")
def wbgt_status(response: Response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return _load_wbgt_status()

@app.get("/wbgt/personalized")
def wbgt_personalized(
    response: Response,
    age: Optional[int] = Query(None, ge=0, le=120, description="user's age in years"),
    is_pregnant: bool = Query(False),
    has_chronic_condition: bool = Query(False),
):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    status = _load_wbgt_status()
    profile = _profile_from_query(age, is_pregnant, has_chronic_condition)
    return classify_for_profile(status["wbgt_c"], profile)

@app.get("/nearby-cool-spots")
def nearby_cool_spots_endpoint(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(800, gt=0, le=5000),
    top_n: int = Query(5, gt=0, le=20),
    age: Optional[int] = Query(None, ge=0, le=120),
    is_pregnant: bool = Query(False),
    has_chronic_condition: bool = Query(False),
):
    profile = _profile_from_query(age, is_pregnant, has_chronic_condition)
    try:
        return nearby_cool_spots(lat, lon, radius_m=radius_m, top_n=top_n, profile=profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/routes/walking")
def walking_routes_endpoint(
    start_lat: float = Query(..., ge=-90, le=90),
    start_lon: float = Query(..., ge=-180, le=180),
    end_lat: float = Query(..., ge=-90, le=90),
    end_lon: float = Query(..., ge=-180, le=180),
    wbgt_c: Optional[float] = Query(None, ge=0, le=60),
    max_detour_pct: float = Query(15, ge=0, le=50),
):
    start = (start_lat, start_lon)
    end = (end_lat, end_lon)
    direct_distance = haversine_m(start, end)
    
    if direct_distance < 20:
        raise HTTPException(status_code=400, detail="Point B must be at least 20 m from Point A")
    if direct_distance > MAX_ROUTE_DISTANCE_M:
        raise HTTPException(
            status_code=400,
            detail=f"Routes are currently limited to {MAX_ROUTE_DISTANCE_M // 1000} km",
        )

    if wbgt_c is None:
        try:
            wbgt_c = float(_load_wbgt_status()["wbgt_c"])
            wbgt_source = "current_status"
        except (HTTPException, KeyError, TypeError, ValueError):
            wbgt_c = 28.0
            wbgt_source = "fallback"
    else:
        wbgt_source = "request"

    try:
        global_graph, node_ids, kd_tree = _load_route_data(str(ROUTE_GRAPH_PATH.resolve()))
        
        # 1. Snap using pre-built fast KD-Tree
        points = gpd.GeoSeries(
            [Point(start_lon, start_lat), Point(end_lon, end_lat)],
            crs="EPSG:4326",
        ).to_crs(global_graph.graph["crs"])
        
        distances, indices = kd_tree.query(np.array([points.x, points.y]).T)
        origin = int(node_ids[indices[0]])
        destination = int(node_ids[indices[1]])
        snap_distances = distances

        if max(snap_distances) > MAX_SNAP_DISTANCE_M:
            raise HTTPException(
                status_code=422,
                detail=(
                    "One or both points are outside the prepared routing area "
                    f"(snap distances: {snap_distances[0]:.0f} m, "
                    f"{snap_distances[1]:.0f} m)."
                ),
            )
        if origin == destination:
            raise HTTPException(
                status_code=400,
                detail="The two points snap to the same street intersection; choose a farther destination.",
            )

        # 2. Extract a local bounding-box subgraph
        ox_x, ox_y = global_graph.nodes[origin]["x"], global_graph.nodes[origin]["y"]
        dx_x, dx_y = global_graph.nodes[destination]["x"], global_graph.nodes[destination]["y"]
        
        padding = max(2000, direct_distance * 0.5)
        min_x, max_x = min(ox_x, dx_x) - padding, max(ox_x, dx_x) + padding
        min_y, max_y = min(ox_y, dx_y) - padding, max(ox_y, dx_y) + padding
        
        local_nodes = [
            n for n, d in global_graph.nodes(data=True)
            if min_x <= d.get("x", 0) <= max_x and min_y <= d.get("y", 0) <= max_y
        ]
        
        # We process math exclusively on the small local slice
        local_graph = global_graph.subgraph(local_nodes)

        routes = calculate_routes(
            local_graph,
            origin,
            destination,
            wbgt_c=wbgt_c,
            max_detour_pct=max_detour_pct,
        )
        return {
            "query": {
                "start": {"lat": start_lat, "lon": start_lon},
                "end": {"lat": end_lat, "lon": end_lon},
                "direct_distance_m": round(direct_distance),
                "max_detour_pct": max_detour_pct,
            },
            "wbgt_c": wbgt_c,
            "wbgt_source": wbgt_source,
            "recommended_route_id": "balanced",
            "routes": serialize_routes(routes),
        }
    except HTTPException:
        raise
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Route calculation failed: {error}") from error

@app.get("/search-places")
def search_places_endpoint(
    q: str = Query(..., min_length=1, description="text the user typed"),
    categories: Optional[str] = Query(
        None,
        description="comma-separated category names to restrict to, e.g. "
                     "'Hospital,Pharmacy'. Omit to search every category.",
    ),
    near_lat: Optional[float] = Query(
        None, ge=-90, le=90, description="usually Point A / current location"
    ),
    near_lon: Optional[float] = Query(None, ge=-180, le=180),
    limit: int = Query(10, gt=0, le=50),
):
    category_list = [c.strip() for c in categories.split(",")] if categories else None
    near = (near_lat, near_lon) if near_lat is not None and near_lon is not None else None
    try:
        return search_places(PLACE_INDEX, q, categories=category_list, limit=limit, near=near)
    except Exception:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="search failed — see server terminal for the traceback")