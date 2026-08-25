"""
============================================================================
Tokyo Open Data Hackathon 2026 — Heat Stroke Prevention Project
OSM_Crop_To_Tokyo.py — shrinks osm_raw/kanto-latest.osm.pbf down to a
Tokyo-only PBF BEFORE pyrosm ever has to touch the full file.

WHY THIS EXISTS: OSM_Tokyo_Extract.py hanging for an hour+ with zero
output on a 467.6 MB Kanto PBF is a known pyrosm failure mode, not a bug
in that script specifically. Two things stack against you there:

  1. pyrosm's own benchmarks (pyrosm.readthedocs.io/en/latest/
     benchmarking.html) state: "With 16GB of RAM ... it should be
     possible to read fairly easily OSM data from Protobuf file up to a
     size of 250 MB." Kanto is 467.6 MB — nearly double that. Their own
     210 MB New York State test took 161-214s; OSMnx on the same data
     was still running after 3 HOURS. pyrosm's `bounding_box=` filter
     does not avoid reading/parsing the full regional file first — for
     a 7-prefecture PBF, that means parsing Ibaraki/Tochigi/Gunma/
     Saitama/Chiba/Kanagawa's data too, just to throw most of it away.
  2. Tokyo_Ward_Boundaries.geojson passed as `bounding_box` is a
     detailed real administrative polygon (traced along the coastline/
     rivers, likely thousands of vertices). If that containment check
     isn't done with a spatial index per node, it can turn into a slow
     per-node polygon test repeated tens of millions of times.

This script sidesteps both: it streams through the PBF ONCE per pass
using pyosmium (not pyrosm) with a plain bounding BOX (four float
comparisons, no polygon math) and writes a small, reference-complete
Tokyo-only PBF. OSM_Tokyo_Extract.py can then apply the PRECISE ward
polygon afterward via pyrosm — cheaply, because by then it's clipping a
small file, not all of Kanto.

Verified end-to-end on real (small-scale) OSM data: crop -> pyrosm
get_network() -> to_graph() -> save/reload -> osmnx routing, all work
against the cropped output.

USAGE:
    pip install osmium   # pyosmium — has prebuilt Windows wheels, no
                          # separate .exe/WSL install needed
    python OSM_Crop_To_Tokyo.py
    python OSM_Tokyo_Extract.py --pbf outputs/Tokyo_Only.osm.pbf

If you want to watch it work rather than take it on faith: this prints
a running node/way count as it streams, so "no output for 40 minutes"
should not happen again — if it does, that itself is a useful data
point (see the troubleshooting note at the bottom of this docstring).

TROUBLESHOOTING: if pass 1 (or 2) itself hangs or is extremely slow on
your machine, check Task Manager's Memory tab while it runs. If memory
climbs steadily toward your total RAM and disk activity spikes (paging/
swap), the machine is memory-constrained, not the code — the fix there
is a smaller input (a Tokyo-prefecture-only PBF from BBBike.org's
custom extract service, instead of the full Kanto file) rather than a
different tool.
============================================================================
"""

import argparse
import time
from pathlib import Path

import geopandas as gpd
import osmium

BASE_DIR = Path(__file__).parent
DEFAULT_PBF = BASE_DIR / "osm_raw" / "kanto-latest.osm.pbf"
DEFAULT_BOUNDARY = BASE_DIR / "outputs" / "Tokyo_Ward_Boundaries.geojson"
OUT_DIR = BASE_DIR / "outputs"
OUT_DIR.mkdir(exist_ok=True)

# Padding added around the boundary's bbox (degrees) so streets that
# cross just outside the ward boundary (e.g. a Tokyo/Kawasaki border
# road) don't get cut mid-way. ~0.02 deg is roughly 2 km at this
# latitude.
BBOX_PAD_DEG = 0.02

FALLBACK_BBOX = (138.94, 35.50, 139.92, 35.90)  # rough Tokyo Metropolis extent

PROGRESS_EVERY = 2_000_000  # print a running count every N nodes/ways


def human(n_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


def load_bbox(boundary_path):
    if boundary_path and boundary_path.exists():
        gdf = gpd.read_file(boundary_path)
        west, south, east, north = gdf.total_bounds
        print(f"  Using bbox from {boundary_path.name}, padded by {BBOX_PAD_DEG} deg")
        return (west - BBOX_PAD_DEG, south - BBOX_PAD_DEG,
                east + BBOX_PAD_DEG, north + BBOX_PAD_DEG)
    print(f"  WARNING: {boundary_path} not found — using a rough Tokyo "
          f"Metropolis bbox {FALLBACK_BBOX} instead.")
    return FALLBACK_BBOX


def nodes_in_bbox(pbf_path, bbox, writer, poi_tag_keys):
    """Single streaming pass over every node:
      - records the ID of every node inside the bbox (needed in pass 2
        to decide which ways to keep)
      - immediately writes any in-bbox node that carries a POI tag we
        care about (railway=*, public_transport=*, amenity=school, ...)
        directly to the output file.

    This second part matters: a station or school is usually mapped as
    a standalone tagged NODE, not part of any way. Relying only on
    BackReferenceWriter's automatic "pull in referenced nodes" (which
    only fires for nodes a kept WAY points to) silently drops every
    standalone POI — caught by testing the full crop -> extract chain,
    not by pass 1 in isolation."""
    west, south, east, north = bbox
    ids = set()
    t0 = time.time()
    n_seen = n_poi = 0
    for node in osmium.FileProcessor(str(pbf_path), osmium.osm.NODE):
        n_seen += 1
        if n_seen % PROGRESS_EVERY == 0:
            print(f"    ...scanned {n_seen:,} nodes "
                  f"({len(ids):,} in bbox, {n_poi:,} POIs kept, "
                  f"{time.time()-t0:.0f}s elapsed)")
        loc = node.location
        if not (loc.valid() and west <= loc.lon <= east and south <= loc.lat <= north):
            continue
        ids.add(node.id)
        if poi_tag_keys and any(k in node.tags for k in poi_tag_keys):
            writer.add_node(node)
            n_poi += 1
    print(f"  pass 1 done: {len(ids):,} of {n_seen:,} nodes are inside "
          f"the bbox, {n_poi:,} standalone POI nodes kept ({time.time()-t0:.0f}s)")
    return ids


def write_cropped_pbf(pbf_path, out_path, bbox, way_filter_tags, poi_tag_keys):
    """Pass 1 (nodes, POI nodes written directly) + pass 2 (ways, with
    BackReferenceWriter pulling in every node a kept way references) —
    both inside one writer session so everything lands in one file."""
    with osmium.BackReferenceWriter(str(out_path), ref_src=str(pbf_path),
                                     overwrite=True) as writer:
        node_ids = nodes_in_bbox(pbf_path, bbox, writer, poi_tag_keys)

        t0 = time.time()
        n_seen = n_matched = 0
        for way in osmium.FileProcessor(str(pbf_path), osmium.osm.WAY):
            n_seen += 1
            if n_seen % PROGRESS_EVERY == 0:
                print(f"    ...scanned {n_seen:,} ways "
                      f"({n_matched:,} matched so far, {time.time()-t0:.0f}s elapsed)")
            tags = way.tags
            if way_filter_tags and not any(t in tags for t in way_filter_tags):
                continue
            if any(n.ref in node_ids for n in way.nodes):
                writer.add_way(way)
                n_matched += 1
        print(f"  pass 2 done: {n_matched:,} of {n_seen:,} ways written "
              f"({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, default=DEFAULT_PBF)
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--out", type=Path, default=OUT_DIR / "Tokyo_Only.osm.pbf")
    parser.add_argument(
        "--all-tags", action="store_true",
        help="Keep every way regardless of tags (bigger, but safe if you also "
             "want buildings/POIs from the cropped file later). Default keeps "
             "highway=*/railway=*/building=*/amenity=*/education=*/office=* ways — "
             "everything "
             "OSM_Tokyo_Extract.py currently uses.",
    )
    args = parser.parse_args()

    if not args.pbf.exists():
        raise FileNotFoundError(f"{args.pbf} not found. Pass --pbf if it's elsewhere.")

    print(f"=== Cropping {args.pbf.name} ({human(args.pbf.stat().st_size)}) ===")
    bbox = load_bbox(args.boundary)
    print(f"  crop bbox: {bbox}")

    way_tags = None if args.all_tags else (
        "highway", "railway", "building", "amenity", "education", "office"
    )
    poi_tags = ("railway", "public_transport", "amenity", "education", "office")
    print(f"\n=== Writing {args.out.name} "
          f"(way filter: {'all tags' if args.all_tags else way_tags}, "
          f"POI node filter: {poi_tags}) ===")
    write_cropped_pbf(args.pbf, args.out, bbox, way_tags, poi_tags)

    size = args.out.stat().st_size
    print(f"\n=== Done. {args.out.name}: {human(size)} "
          f"(was {human(args.pbf.stat().st_size)}) ===")
    print(f"Next: python OSM_Tokyo_Extract.py --pbf {args.out}")