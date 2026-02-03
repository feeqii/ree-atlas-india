from typing import Dict, Tuple
import numpy as np
import xarray as xr


def _percentile_scale(arr: xr.DataArray, p_low: float, p_high: float) -> xr.DataArray:
    data = arr.values.astype("float32")
    lo = np.nanpercentile(data, p_low)
    hi = np.nanpercentile(data, p_high)
    if hi - lo == 0:
        scaled = np.zeros_like(data)
    else:
        scaled = (data - lo) / (hi - lo)
    scaled = np.clip(scaled, 0, 1)
    return arr.copy(data=scaled)


def coastal_score(
    ndvi: xr.DataArray,
    ndwi: xr.DataArray,
    bsi: xr.DataArray,
    slope: xr.DataArray,
    dist_coast_m: xr.DataArray,
    dist_river_m: xr.DataArray,
    params: Dict,
) -> Tuple[xr.DataArray, Dict]:
    thresholds = {
        "coast_max_m": params.get("coast_max_m", 30_000),
        "slope_max": params.get("slope_max", 5.0),
        "ndvi_max": params.get("ndvi_max", 0.2),
        "bsi_percentile": params.get("bsi_percentile", 70),
        "river_max_m": params.get("river_max_m", 10_000),
        "ndwi_water_max": params.get("ndwi_water_max", 0.1),
    }
    weights = params.get(
        "weights",
        {
            "coastal_proximity": 0.30,
            "slope": 0.20,
            "bare_land": 0.20,
            "sandiness": 0.20,
            "river_proximity": 0.10,
        },
    )

    coastal_score = 1.0 - (dist_coast_m / thresholds["coast_max_m"])
    coastal_score = coastal_score.clip(0, 1)

    slope_score = 1.0 - (slope / thresholds["slope_max"])
    slope_score = slope_score.clip(0, 1)

    bare_land_score = 1.0 - (ndvi / thresholds["ndvi_max"])
    bare_land_score = bare_land_score.clip(0, 1)

    sandiness_score = _percentile_scale(bsi, thresholds["bsi_percentile"], 98)

    river_score = 1.0 - (dist_river_m / thresholds["river_max_m"])
    river_score = river_score.clip(0, 1)

    score = (
        coastal_score * weights["coastal_proximity"]
        + slope_score * weights["slope"]
        + bare_land_score * weights["bare_land"]
        + sandiness_score * weights["sandiness"]
        + river_score * weights["river_proximity"]
    )

    water_mask = (ndwi < thresholds["ndwi_water_max"]).astype("float32")
    score = score * water_mask
    score = score.clip(0, 1)

    meta = {
        "mode": "coastal",
        "weights": weights,
        "thresholds": thresholds,
    }
    layers = {
        "coastal_score": coastal_score,
        "slope_score": slope_score,
        "bare_land_score": bare_land_score,
        "sandiness_score": sandiness_score,
        "river_score": river_score,
        "water_mask": water_mask,
    }
    return score, {"meta": meta, "layers": layers}


def hardrock_score(
    ndvi: xr.DataArray,
    ndwi: xr.DataArray,
    slope: xr.DataArray,
    lineaments: xr.DataArray,
    geology_mask: xr.DataArray,
    params: Dict,
) -> Tuple[xr.DataArray, Dict]:
    thresholds = {
        "lineament_percentile": params.get("lineament_percentile", 70),
        "slope_min": params.get("slope_min", 2.0),
        "slope_max": params.get("slope_max", 25.0),
        "ndvi_max": params.get("ndvi_max", 0.4),
        "ndwi_water_max": params.get("ndwi_water_max", 0.1),
    }
    weights = params.get(
        "weights",
        {
            "lineaments": 0.45,
            "relief": 0.20,
            "exposure": 0.20,
            "geology_boost": 0.15,
        },
    )

    lineament_score = _percentile_scale(lineaments, thresholds["lineament_percentile"], 98)

    relief_score = ((slope >= thresholds["slope_min"]) & (slope <= thresholds["slope_max"])).astype("float32")

    exposure_score = 1.0 - (ndvi / thresholds["ndvi_max"])
    exposure_score = exposure_score.clip(0, 1)

    geology_score = geology_mask if geology_mask is not None else None

    if geology_score is None:
        total = weights["lineaments"] + weights["relief"] + weights["exposure"]
        w_line = weights["lineaments"] / total
        w_relief = weights["relief"] / total
        w_exposure = weights["exposure"] / total
        w_geo = 0.0
    else:
        w_line = weights["lineaments"]
        w_relief = weights["relief"]
        w_exposure = weights["exposure"]
        w_geo = weights["geology_boost"]

    score = lineament_score * w_line + relief_score * w_relief + exposure_score * w_exposure
    if geology_score is not None:
        score = score + geology_score * w_geo

    water_mask = (ndwi < thresholds["ndwi_water_max"]).astype("float32")
    score = score * water_mask
    score = score.clip(0, 1)

    meta = {
        "mode": "hardrock",
        "weights": {
            "lineaments": w_line,
            "relief": w_relief,
            "exposure": w_exposure,
            "geology_boost": w_geo,
        },
        "thresholds": thresholds,
    }
    layers = {
        "lineament_score": lineament_score,
        "relief_score": relief_score,
        "exposure_score": exposure_score,
        "geology_score": geology_score,
        "water_mask": water_mask,
    }
    return score, {"meta": meta, "layers": layers}
