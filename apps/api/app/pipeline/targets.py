from typing import Dict, List, Tuple
import uuid

import numpy as np
import xarray as xr
from rasterio import features
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_transform
import pyproj
import geopandas as gpd


def _geom_mask(geom, ref_da: xr.DataArray) -> np.ndarray:
    return features.geometry_mask(
        [mapping(geom)],
        out_shape=(ref_da.shape[-2], ref_da.shape[-1]),
        transform=ref_da.rio.transform(),
        invert=True,
    )


def _area_km2(geom) -> float:
    geod = pyproj.Geod(ellps="WGS84")
    area, _ = geod.geometry_area_perimeter(geom)
    return abs(area) / 1_000_000.0


def _centroid_wkt(geom) -> str:
    return geom.centroid.wkt


def _distance_to_lines(geom, gdf: gpd.GeoDataFrame) -> float:
    if gdf is None or gdf.empty:
        return None
    # project to UTM for meters
    centroid = geom.centroid
    utm_crs = _utm_crs_from_lonlat(centroid.x, centroid.y)
    project = pyproj.Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True).transform
    geom_proj = shp_transform(project, geom)
    gdf_proj = gdf.to_crs(utm_crs)
    union = gdf_proj.geometry.unary_union
    return geom_proj.distance(union)


def _utm_crs_from_lonlat(lon, lat) -> str:
    zone = int((lon + 180) / 6) + 1
    hemisphere = "326" if lat >= 0 else "327"
    return f"EPSG:{hemisphere}{zone:02d}"


def extract_targets(
    score_da: xr.DataArray,
    threshold: float,
    min_area_km2: float,
    mode: str,
    evidence_layers: Dict[str, xr.DataArray],
    thresholds: Dict[str, float],
    roads_gdf: gpd.GeoDataFrame,
    rivers_gdf: gpd.GeoDataFrame,
) -> List[Dict]:
    score = score_da.values.astype("float32")
    mask = score >= threshold

    # Remove small objects in pixel count
    from skimage.morphology import remove_small_objects

    # estimate pixel area in km2
    xres, yres = score_da.rio.resolution()
    crs = score_da.rio.crs
    if crs and str(crs) == "EPSG:4326":
        from shapely.geometry import Polygon
        from affine import Affine

        transform = score_da.rio.transform()
        x0, y0 = transform * (0, 0)
        x1, y1 = transform * (1, 1)
        poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])
        pixel_area_km2 = _area_km2(poly)
    else:
        pixel_area_km2 = abs(xres * yres) / 1_000_000.0
    min_size_px = max(int(min_area_km2 / pixel_area_km2), 1)
    mask = remove_small_objects(mask, min_size=min_size_px)

    shapes = features.shapes(mask.astype("uint8"), mask=mask, transform=score_da.rio.transform())

    targets = []
    for geom, val in shapes:
        if val != 1:
            continue
        poly = shape(geom)
        area_km2 = _area_km2(poly)
        if area_km2 < min_area_km2:
            continue

        poly_mask = _geom_mask(poly, score_da)
        poly_scores = score[poly_mask]
        mean_score = float(np.nanmean(poly_scores))
        max_score = float(np.nanmax(poly_scores))

        evidence = compute_evidence(poly_mask, evidence_layers, thresholds, mode)
        chips = evidence_chips(evidence, mode)

        targets.append(
            {
                "id": str(uuid.uuid4()),
                "geometry": poly,
                "area_km2": area_km2,
                "centroid": poly.centroid,
                "mean_score": mean_score,
                "max_score": max_score,
                "distance_to_road_m": _distance_to_lines(poly, roads_gdf),
                "distance_to_river_m": _distance_to_lines(poly, rivers_gdf),
                "evidence": evidence,
                "evidence_summary": chips,
            }
        )

    targets.sort(key=lambda t: (t["mean_score"], t["area_km2"]), reverse=True)
    return targets


def compute_evidence(poly_mask: np.ndarray, layers: Dict[str, xr.DataArray], thresholds: Dict[str, float], mode: str) -> Dict:
    def _mean(name):
        arr = layers[name].values
        return float(np.nanmean(arr[poly_mask]))

    def _pct(name, op, thr):
        arr = layers[name].values
        vals = arr[poly_mask]
        if vals.size == 0:
            return 0.0
        if op == "<":
            return float(np.mean(vals < thr))
        if op == "<=":
            return float(np.mean(vals <= thr))
        if op == ">":
            return float(np.mean(vals > thr))
        if op == ">=":
            return float(np.mean(vals >= thr))
        return 0.0

    if mode == "coastal":
        ev = {
            "ndvi_mean": _mean("ndvi"),
            "ndwi_mean": _mean("ndwi"),
            "bsi_mean": _mean("bsi"),
            "slope_mean": _mean("slope"),
            "dist_coast_mean_m": _mean("dist_coast"),
            "dist_river_mean_m": _mean("dist_river"),
            "pct_low_slope": _pct("slope", "<=", thresholds["slope_max"]),
            "pct_low_ndvi": _pct("ndvi", "<=", thresholds["ndvi_max"]),
            "pct_high_bsi": _pct("bsi", ">=", thresholds["bsi_threshold_value"]),
            "pct_near_coast": _pct("dist_coast", "<=", thresholds["coast_max_m"]),
            "pct_near_river": _pct("dist_river", "<=", thresholds["river_max_m"]),
        }
    else:
        vals = layers["slope"].values[poly_mask]
        pct_relief = 0.0
        if vals.size > 0:
            pct_relief = float(((vals >= thresholds["slope_min"]) & (vals <= thresholds["slope_max"])).mean())

        ev = {
            "ndvi_mean": _mean("ndvi"),
            "ndwi_mean": _mean("ndwi"),
            "slope_mean": _mean("slope"),
            "lineament_mean": _mean("lineaments"),
            "geology_mask_mean": _mean("geology_mask") if "geology_mask" in layers else 0.0,
            "pct_lineament_high": _pct("lineaments", ">=", thresholds["lineament_threshold_value"]),
            "pct_relief": pct_relief,
            "pct_low_ndvi": _pct("ndvi", "<=", thresholds["ndvi_max"]),
            "pct_geology_match": _pct("geology_mask", ">=", 0.5) if "geology_mask" in layers else 0.0,
        }
    return ev


def evidence_chips(evidence: Dict, mode: str) -> List[str]:
    candidates = []
    if mode == "coastal":
        candidates.append(("Near coastline (<30 km)", evidence.get("pct_near_coast", 0)))
        candidates.append(("Low slope (<=5°)", evidence.get("pct_low_slope", 0)))
        candidates.append(("Low vegetation (NDVI<=0.2)", evidence.get("pct_low_ndvi", 0)))
        candidates.append(("High sandiness (BSI top 30%)", evidence.get("pct_high_bsi", 0)))
        candidates.append(("Near rivers", evidence.get("pct_near_river", 0)))
    else:
        candidates.append(("High lineament density", evidence.get("pct_lineament_high", 0)))
        candidates.append(("Moderate relief (2–25°)", evidence.get("pct_relief", 0)))
        candidates.append(("Low vegetation (NDVI<=0.4)", evidence.get("pct_low_ndvi", 0)))
        if evidence.get("pct_geology_match", 0) > 0:
            candidates.append(("Favorable lithology match", evidence.get("pct_geology_match", 0)))

    candidates.sort(key=lambda x: x[1], reverse=True)
    chips = [c[0] for c in candidates[:3] if c[1] > 0]
    return chips
