import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pyproj
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_transform


def ensure_dir(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def aoi_bounds(aoi_geojson: Dict) -> Tuple[float, float, float, float]:
    geom = shape(aoi_geojson.get("geometry", aoi_geojson))
    return geom.bounds


def aoi_area_km2(aoi_geojson: Dict) -> float:
    geom = shape(aoi_geojson.get("geometry", aoi_geojson))
    # Use equal area projection for rough area
    proj = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True).transform
    geom_eq = shp_transform(proj, geom)
    return abs(geom_eq.area) / 1_000_000.0


def utm_crs_from_lonlat(lon: float, lat: float) -> str:
    zone = int((lon + 180) / 6) + 1
    hemisphere = "326" if lat >= 0 else "327"
    return f"EPSG:{hemisphere}{zone:02d}"


def hash_str(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def normalize_minmax(arr: np.ndarray, min_val: float = None, max_val: float = None) -> np.ndarray:
    a = arr.astype("float32")
    if min_val is None:
        min_val = np.nanmin(a)
    if max_val is None:
        max_val = np.nanmax(a)
    if max_val - min_val == 0:
        return np.zeros_like(a)
    return np.clip((a - min_val) / (max_val - min_val), 0, 1)


def scale_to_uint8(arr: np.ndarray, pmin: float = 2, pmax: float = 98) -> np.ndarray:
    a = arr.astype("float32")
    lo = np.nanpercentile(a, pmin)
    hi = np.nanpercentile(a, pmax)
    if hi - lo == 0:
        return np.zeros_like(a, dtype=np.uint8)
    scaled = np.clip((a - lo) / (hi - lo), 0, 1)
    return (scaled * 255).astype(np.uint8)


def safe_json_dump(obj: Dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

