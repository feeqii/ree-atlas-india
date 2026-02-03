import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
import rioxarray as rxr
import xarray as xr
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from shapely.geometry import mapping

from .stac import load_sentinel_composite, load_dem
from .dem import compute_slope, compute_hillshade, reproject_to_match
from .osm import fetch_osm_lines, save_geojson
from .features import compute_indices, distance_raster, lineament_density
from .scoring import coastal_score, hardrock_score
from .targets import extract_targets
from .overlay import save_score_overlay, save_rgb_preview, save_hillshade
from .report import render_report
from .utils import ensure_dir, aoi_bounds, aoi_area_km2, utm_crs_from_lonlat, safe_json_dump
from ..settings import settings


def _default_time_range():
    end = datetime.utcnow().date()
    start = end - timedelta(days=365)
    return f"{start.isoformat()}/{end.isoformat()}"


def _save_da(da: xr.DataArray, path: str):
    da.rio.to_raster(path)


def _synthetic_sentinel(aoi_geojson: Dict, width: int = 256, height: int = 256) -> xr.DataArray:
    minx, miny, maxx, maxy = aoi_bounds(aoi_geojson)
    transform = from_bounds(minx, miny, maxx, maxy, width, height)
    x = np.linspace(minx, maxx, width)
    y = np.linspace(maxy, miny, height)
    xv, yv = np.meshgrid(x, y)
    base = (np.sin(xv * 10) + np.cos(yv * 10)) * 0.5 + 0.5
    noise = np.random.default_rng(42).normal(scale=0.05, size=base.shape)
    def band(scale, bias):
        return np.clip(base * scale + bias + noise, 0, 1).astype("float32")

    bands = {
        "B2": band(0.6, 0.1),
        "B3": band(0.7, 0.1),
        "B4": band(0.8, 0.05),
        "B8": band(0.9, 0.02),
        "B11": band(0.7, 0.08),
    }
    da = xr.DataArray(
        np.stack([bands[k] for k in bands.keys()], axis=0),
        dims=("band", "y", "x"),
        coords={"band": list(bands.keys()), "y": y, "x": x},
    )
    da.rio.write_transform(transform, inplace=True)
    da.rio.write_crs("EPSG:4326", inplace=True)
    return da


def _synthetic_dem(ref_da: xr.DataArray) -> xr.DataArray:
    y = ref_da.coords["y"].values
    x = ref_da.coords["x"].values
    xv, yv = np.meshgrid(x, y)
    dem = (xv - xv.min()) * 10 + (yv - yv.min()) * 5
    return ref_da.isel(band=0).copy(data=dem.astype("float32"))


def _rasterize_geology(geology_geojson: Dict, ref_da: xr.DataArray) -> Optional[xr.DataArray]:
    if not geology_geojson:
        return None
    keywords = [
        "carbonatite",
        "alkaline",
        "syenite",
        "ijolite",
        "nepheline",
        "granite pegmatite",
        "ree",
        "monazite",
        "bastnaesite",
    ]
    import geopandas as gpd
    from shapely.geometry import shape

    records = []
    for feat in geology_geojson.get("features", []):
        props = feat.get("properties", {})
        text = " ".join([str(v) for v in props.values()]).lower()
        if any(k in text for k in keywords):
            geom = feat.get("geometry")
            if geom:
                records.append({"geometry": shape(geom)})
    if not records:
        return None

    gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    if ref_da.rio.crs:
        gdf = gdf.to_crs(ref_da.rio.crs)
    shapes = [(geom, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty]
    if not shapes:
        return None

    mask = rasterize(
        shapes,
        out_shape=(ref_da.shape[-2], ref_da.shape[-1]),
        transform=ref_da.rio.transform(),
        fill=0,
        dtype="uint8",
    )
    return ref_da.copy(data=mask.astype("float32"))


def run_pipeline(run_id: str, aoi_geojson: Dict, mode: str, params: Dict, geology_geojson: Optional[Dict] = None,
                 progress_cb=None):
    run_dir = ensure_dir(os.path.join(settings.data_dir, "runs", run_id))
    cache_dir = ensure_dir(os.path.join(settings.data_dir, "cache"))

    safe_json_dump(aoi_geojson, os.path.join(run_dir, "aoi.geojson"))

    if progress_cb:
        progress_cb("fetch_imagery")

    time_range = params.get("time_range") or _default_time_range()
    cloud_max = params.get("cloud_cover_max", 40.0)

    cache_enabled = bool(params.get("cache_downloads", False))
    use_synth = bool(params.get("use_synthetic", False))
    if use_synth:
        s2_da = _synthetic_sentinel(aoi_geojson, width=int(params.get("synthetic_width", 256)),
                                    height=int(params.get("synthetic_height", 256)))
    else:
        s2_da, bands = load_sentinel_composite(
            settings.stac_api_url,
            settings.stac_collection_s2,
            aoi_geojson,
            time_range,
            cache_dir=cache_dir,
            cache_enabled=cache_enabled,
            cloud_cover_max=cloud_max,
            max_items=int(params.get("max_items", 3)),
        )

    s2_path = os.path.join(run_dir, "sentinel_composite.tif")
    _save_da(s2_da, s2_path)

    ndvi, ndwi, bsi = compute_indices(s2_da)
    _save_da(ndvi, os.path.join(run_dir, "ndvi.tif"))
    _save_da(ndwi, os.path.join(run_dir, "ndwi.tif"))
    _save_da(bsi, os.path.join(run_dir, "bsi.tif"))

    if progress_cb:
        progress_cb("fetch_dem")

    try:
        if use_synth:
            dem_da = _synthetic_dem(s2_da)
        else:
            dem_da = load_dem(settings.stac_api_url, [c.strip() for c in settings.stac_collection_dem.split(",")],
                             aoi_geojson, cache_dir=cache_dir, cache_enabled=cache_enabled)
    except Exception:
        # fallback flat DEM if not available
        dem_da = s2_da.isel(band=0).copy(data=np.zeros_like(s2_da.isel(band=0).values))

    dem_da = reproject_to_match(dem_da, s2_da.isel(band=0))
    _save_da(dem_da, os.path.join(run_dir, "dem.tif"))

    slope = compute_slope(dem_da)
    hillshade = compute_hillshade(dem_da)
    _save_da(slope, os.path.join(run_dir, "slope.tif"))
    _save_da(hillshade, os.path.join(run_dir, "hillshade.tif"))

    if progress_cb:
        progress_cb("fetch_osm")

    bounds = aoi_bounds(aoi_geojson)
    osm_timeout = int(params.get("osm_timeout_s", 40))
    roads, rivers, coast = fetch_osm_lines(bounds, timeout_s=osm_timeout)
    save_geojson(roads, os.path.join(run_dir, "roads.geojson"))
    save_geojson(rivers, os.path.join(run_dir, "rivers.geojson"))
    save_geojson(coast, os.path.join(run_dir, "coast.geojson"))

    dist_roads = distance_raster(roads, s2_da.isel(band=0))
    dist_rivers = distance_raster(rivers, s2_da.isel(band=0))
    dist_coast = distance_raster(coast, s2_da.isel(band=0))
    _save_da(dist_roads, os.path.join(run_dir, "dist_roads.tif"))
    _save_da(dist_rivers, os.path.join(run_dir, "dist_rivers.tif"))
    _save_da(dist_coast, os.path.join(run_dir, "dist_coast.tif"))

    if progress_cb:
        progress_cb("compute_features")

    lineaments = None
    geology_mask = _rasterize_geology(geology_geojson, s2_da.isel(band=0))
    if mode == "hardrock":
        lineaments = lineament_density(hillshade)
        _save_da(lineaments, os.path.join(run_dir, "lineaments.tif"))
        if geology_mask is not None:
            _save_da(geology_mask, os.path.join(run_dir, "geology_mask.tif"))

    if progress_cb:
        progress_cb("score")

    if mode == "coastal":
        score, score_meta = coastal_score(ndvi, ndwi, bsi, slope, dist_coast, dist_rivers, params)
        thresholds = score_meta["meta"]["thresholds"].copy()
        thresholds["bsi_threshold_value"] = float(np.nanpercentile(bsi.values, thresholds["bsi_percentile"]))
        thresholds["coast_max_m"] = thresholds["coast_max_m"]
        thresholds["river_max_m"] = thresholds["river_max_m"]
        evidence_layers = {
            "ndvi": ndvi,
            "ndwi": ndwi,
            "bsi": bsi,
            "slope": slope,
            "dist_coast": dist_coast,
            "dist_river": dist_rivers,
        }
    else:
        score, score_meta = hardrock_score(ndvi, ndwi, slope, lineaments, geology_mask, params)
        thresholds = score_meta["meta"]["thresholds"].copy()
        thresholds["lineament_threshold_value"] = float(np.nanpercentile(lineaments.values, thresholds["lineament_percentile"]))
        evidence_layers = {
            "ndvi": ndvi,
            "ndwi": ndwi,
            "slope": slope,
            "lineaments": lineaments,
        }
        if geology_mask is not None:
            evidence_layers["geology_mask"] = geology_mask

    _save_da(score, os.path.join(run_dir, "score.tif"))

    if progress_cb:
        progress_cb("extract_targets")

    threshold_method = params.get("threshold_method", "percentile")
    if threshold_method == "fixed":
        threshold_value = float(params.get("fixed_threshold", 0.7))
    else:
        percentile = float(params.get("target_percentile", 95))
        threshold_value = float(np.nanpercentile(score.values, percentile))

    min_area_km2 = float(params.get("min_area_km2", 0.1))

    targets = extract_targets(
        score,
        threshold_value,
        min_area_km2,
        mode,
        evidence_layers,
        thresholds,
        roads,
        rivers,
    )

    if progress_cb:
        progress_cb("generate_outputs")

    # overlays
    overlay_path = os.path.join(run_dir, "overlay.png")
    overlay_bbox = save_score_overlay(score, overlay_path)

    # preview images
    r = s2_da.sel(band="B4")
    g = s2_da.sel(band="B3")
    b = s2_da.sel(band="B2")
    sentinel_path = os.path.join(run_dir, "sentinel_preview.png")
    save_rgb_preview(r, g, b, sentinel_path)

    hillshade_path = os.path.join(run_dir, "dem_hillshade.png")
    save_hillshade(hillshade, hillshade_path)

    # exports
    targets_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": json.loads(json.dumps(mapping(t["geometry"]))),
                "properties": {
                    "id": t["id"],
                    "area_km2": t["area_km2"],
                    "mean_score": t["mean_score"],
                    "max_score": t["max_score"],
                    "distance_to_road_m": t["distance_to_road_m"],
                    "distance_to_river_m": t["distance_to_river_m"],
                    "evidence_summary": t["evidence_summary"],
                },
            }
            for t in targets
        ],
    }
    safe_json_dump(targets_geojson, os.path.join(run_dir, "targets.geojson"))

    df = pd.DataFrame(
        [
            {
                "id": t["id"],
                "centroid_lat": t["centroid"].y,
                "centroid_lon": t["centroid"].x,
                "area_km2": t["area_km2"],
                "mean_score": t["mean_score"],
                "max_score": t["max_score"],
                "distance_to_road_m": t["distance_to_road_m"],
                "distance_to_river_m": t["distance_to_river_m"],
                "evidence_summary": ";".join(t["evidence_summary"] or []),
            }
            for t in targets
        ]
    )
    df.to_csv(os.path.join(run_dir, "targets.csv"), index=False)

    report_path = render_report(
        run_dir,
        {
            "id": run_id,
            "mode": mode,
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
            "overlay_path": overlay_path,
            "sentinel_preview_path": sentinel_path,
            "hillshade_path": hillshade_path,
        },
        targets,
    )

    score_meta_clean = score_meta["meta"]
    score_meta_clean["thresholds"] = thresholds
    safe_json_dump(score_meta_clean, os.path.join(run_dir, "score_meta.json"))

    return {
        "overlay_path": overlay_path,
        "overlay_bbox": overlay_bbox,
        "sentinel_preview_path": sentinel_path,
        "hillshade_path": hillshade_path,
        "report_path": report_path,
        "targets": targets,
        "score_meta": score_meta_clean,
    }
