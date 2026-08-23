import tempfile
import unittest
from pathlib import Path

import networkx as nx
from shapely.geometry import LineString

from Cool_Route import (
    calculate_routes,
    export_routes,
    haversine_m,
    serialize_routes,
    wbgt_multiplier,
)


SCORE_DEFAULTS = {
    "nearby_tree_count": 0,
    "tree_score": 0.0,
    "park_score": 0.0,
    "protected_green_score": 0.0,
    "housing_green_score": 0.0,
    "facility_green_score": 0.0,
    "water_score": 0.0,
    "station_score": 0.0,
}


def add_edge(graph, u, v, coordinates, length, exposure):
    graph.add_edge(
        u,
        v,
        key=0,
        geometry=LineString(coordinates),
        length=length,
        length_m=length,
        heat_exposure=exposure,
        cooling_score=1 - exposure,
        **SCORE_DEFAULTS,
    )


def synthetic_graph():
    graph = nx.MultiDiGraph(crs="EPSG:3857", simplified=True)
    graph.add_node(0, x=0.0, y=0.0)
    graph.add_node(1, x=100.0, y=0.0)
    graph.add_node(2, x=50.0, y=40.0)

    # Direct: 100 m but exposed. Alternative: 120 m but much cooler.
    add_edge(graph, 0, 1, [(0, 0), (100, 0)], 100.0, 1.0)
    add_edge(graph, 0, 2, [(0, 0), (50, 40)], 60.0, 0.1)
    add_edge(graph, 2, 1, [(50, 40), (100, 0)], 60.0, 0.1)
    return graph


class CoolRouteTests(unittest.TestCase):
    def test_distance_and_wbgt_helpers(self):
        self.assertAlmostEqual(haversine_m((35.0, 139.0), (35.0, 139.0)), 0.0)
        self.assertLess(wbgt_multiplier(20), wbgt_multiplier(31))

    def test_balanced_route_respects_detour_limit(self):
        routes = calculate_routes(synthetic_graph(), 0, 1, wbgt_c=31, max_detour_pct=15)
        self.assertAlmostEqual(routes["shortest"]["summary"]["length_m"], 100.0)
        self.assertAlmostEqual(routes["coolest"]["summary"]["length_m"], 120.0)
        self.assertAlmostEqual(routes["balanced"]["summary"]["length_m"], 100.0)

    def test_balanced_route_selects_cooler_route_when_allowed(self):
        graph = synthetic_graph()
        routes = calculate_routes(graph, 0, 1, wbgt_c=31, max_detour_pct=25)
        self.assertAlmostEqual(routes["balanced"]["summary"]["length_m"], 120.0)
        self.assertLess(
            routes["balanced"]["summary"]["heat_exposure_index"],
            routes["shortest"]["summary"]["heat_exposure_index"],
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "routes.geojson"
            export_routes(
                routes,
                graph.graph["crs"],
                (0.0, 0.0),
                (0.0, 0.001),
                31.0,
                output,
            )
            self.assertTrue(output.exists())

    def test_routes_serialize_to_leaflet_coordinates(self):
        routes = calculate_routes(synthetic_graph(), 0, 1, wbgt_c=31, max_detour_pct=25)
        payload = serialize_routes(routes)

        self.assertEqual([route["id"] for route in payload], ["shortest", "coolest", "balanced"])
        self.assertEqual(payload[0]["distance_m"], 100)
        self.assertEqual(payload[0]["coords"][0][0], [0.0, 0.0])
        self.assertGreater(len(payload[1]["coords"]), 0)


if __name__ == "__main__":
    unittest.main()
