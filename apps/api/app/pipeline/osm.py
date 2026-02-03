import json
from typing import Dict, Tuple

import geopandas as gpd
import requests
from shapely.geometry import LineString

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _bbox_str(bounds: Tuple[float, float, float, float]) -> str:
    minx, miny, maxx, maxy = bounds
    return f"{miny},{minx},{maxy},{maxx}"


def fetch_osm_lines(bounds: Tuple[float, float, float, float], timeout_s: int = 60):
    bbox = _bbox_str(bounds)
    query = f"""
    [out:json][timeout:90];
    (
      way["highway"]({bbox});
      way["waterway"~"river|stream"]({bbox});
      way["natural"="coastline"]({bbox});
    );
    out geom;
    """
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=timeout_s)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return (
            gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"),
            gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"),
            gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"),
        )

    roads = []
    rivers = []
    coast = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        coords = el.get("geometry")
        if not coords:
            continue
        line = LineString([(c["lon"], c["lat"]) for c in coords])
        tags = el.get("tags", {})
        if "highway" in tags:
            roads.append(line)
        elif tags.get("waterway") in ["river", "stream"]:
            rivers.append(line)
        elif tags.get("natural") == "coastline":
            coast.append(line)

    roads_gdf = gpd.GeoDataFrame(geometry=roads, crs="EPSG:4326")
    rivers_gdf = gpd.GeoDataFrame(geometry=rivers, crs="EPSG:4326")
    coast_gdf = gpd.GeoDataFrame(geometry=coast, crs="EPSG:4326")
    return roads_gdf, rivers_gdf, coast_gdf


def save_geojson(gdf, path: str):
    if gdf is None:
        return
    gdf.to_file(path, driver="GeoJSON")
