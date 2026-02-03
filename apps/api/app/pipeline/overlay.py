import base64
from io import BytesIO
from typing import Dict, Tuple

import numpy as np
from PIL import Image
import pyproj
import rasterio

from .utils import scale_to_uint8


def raster_bounds_latlon(da) -> Dict:
    transform = da.rio.transform()
    height, width = da.shape[-2], da.shape[-1]
    left, bottom, right, top = rasterio.transform.array_bounds(height, width, transform)
    src_crs = da.rio.crs
    if str(src_crs) != "EPSG:4326":
        transformer = pyproj.Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
        (left, bottom) = transformer.transform(left, bottom)
        (right, top) = transformer.transform(right, top)
    return {"minx": left, "miny": bottom, "maxx": right, "maxy": top}


def save_score_overlay(score_da, path: str) -> Dict:
    score = score_da.values.astype("float32")
    score = np.clip(score, 0, 1)
    gray = (score * 255).astype(np.uint8)
    alpha = (score * 255).astype(np.uint8)
    rgba = np.stack([gray, gray, gray, alpha], axis=-1)
    img = Image.fromarray(rgba, mode="RGBA")
    img.save(path)
    return raster_bounds_latlon(score_da)


def save_rgb_preview(r_da, g_da, b_da, path: str) -> Dict:
    r = scale_to_uint8(r_da.values)
    g = scale_to_uint8(g_da.values)
    b = scale_to_uint8(b_da.values)
    rgb = np.stack([r, g, b], axis=-1)
    img = Image.fromarray(rgb, mode="RGB")
    img.save(path)
    return raster_bounds_latlon(r_da)


def save_hillshade(hillshade_da, path: str) -> Dict:
    gray = (np.clip(hillshade_da.values, 0, 1) * 255).astype(np.uint8)
    img = Image.fromarray(gray, mode="L")
    img.save(path)
    return raster_bounds_latlon(hillshade_da)


def image_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return encoded
