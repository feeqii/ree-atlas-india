import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import rioxarray as rxr
import xarray as xr
from pystac_client import Client
from shapely.geometry import shape
from rasterio.enums import Resampling

try:
    import planetary_computer
except Exception:  # pragma: no cover - optional for non-PC endpoints
    planetary_computer = None

from .utils import ensure_dir, hash_str


SENTINEL_BANDS = {
    "B2": "blue",
    "B3": "green",
    "B4": "red",
    "B8": "nir",
    "B11": "swir",
}

BAND_ALIASES = {
    "B2": ["B02", "B2"],
    "B3": ["B03", "B3"],
    "B4": ["B04", "B4"],
    "B8": ["B08", "B8"],
    "B11": ["B11", "B011", "B11"],
}


def _sign_item(item, stac_api_url: str):
    if planetary_computer and "planetarycomputer" in stac_api_url:
        return planetary_computer.sign(item)
    return item


def search_items(stac_api_url: str, collection: str, aoi_geojson: Dict, time_range: str, max_items: int = 5,
                 cloud_cover_max: Optional[float] = 40.0):
    client = Client.open(stac_api_url)
    search = client.search(
        collections=[collection],
        intersects=aoi_geojson.get("geometry", aoi_geojson),
        datetime=time_range,
        max_items=50,
    )
    items = list(search.items())
    if not items:
        return []

    if cloud_cover_max is not None:
        filtered = []
        for it in items:
            cc = it.properties.get("eo:cloud_cover")
            if cc is None or cc <= cloud_cover_max:
                filtered.append(it)
        items = filtered or items

    items.sort(key=lambda i: i.properties.get("eo:cloud_cover", 1000))
    return items[:max_items]


def _localize_asset(href: str, cache_dir: str, cache_enabled: bool) -> str:
    if not cache_enabled:
        return href
    ensure_dir(cache_dir)
    fname = f"{hash_str(href)}.tif"
    path = os.path.join(cache_dir, fname)
    if os.path.exists(path):
        return path
    import requests

    with requests.get(href, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    return path


def _get_asset(item, band: str):
    aliases = BAND_ALIASES.get(band, [band])
    for key in aliases:
        if key in item.assets:
            return item.assets[key]
    raise KeyError(band)


def _read_band(item, band: str, aoi_geojson: Dict, ref=None, cache_dir: str = None,
               cache_enabled: bool = True) -> xr.DataArray:
    asset = _get_asset(item, band)
    href = asset.href
    if cache_dir:
        href = _localize_asset(href, cache_dir, cache_enabled)
    da = rxr.open_rasterio(href, masked=True).squeeze()
    da = da.rio.clip([shape(aoi_geojson.get("geometry", aoi_geojson))], crs="EPSG:4326", drop=True)
    if ref is not None:
        da = da.rio.reproject_match(ref, resampling=Resampling.bilinear)
    return da


def load_sentinel_composite(
    stac_api_url: str,
    collection: str,
    aoi_geojson: Dict,
    time_range: str,
    cache_dir: str,
    cache_enabled: bool = True,
    cloud_cover_max: Optional[float] = 40.0,
    max_items: int = 5,
) -> Tuple[xr.DataArray, List[str]]:
    items = search_items(stac_api_url, collection, aoi_geojson, time_range, max_items=max_items,
                         cloud_cover_max=cloud_cover_max)
    if not items:
        raise RuntimeError("No Sentinel-2 items found for AOI/time range")
    signed_items = [_sign_item(it, stac_api_url) for it in items]

    # Reference grid from first item's B4 band
    ref = _read_band(signed_items[0], "B4", aoi_geojson, cache_dir=cache_dir, cache_enabled=cache_enabled)

    bands_out = []
    band_names = []
    for band in ["B2", "B3", "B4", "B8", "B11"]:
        stack = []
        for item in signed_items:
            da = _read_band(item, band, aoi_geojson, ref=ref, cache_dir=cache_dir, cache_enabled=cache_enabled)
            stack.append(da)
        band_stack = xr.concat(stack, dim="time").median(dim="time", skipna=True)
        bands_out.append(band_stack)
        band_names.append(band)

    da = xr.concat(bands_out, dim="band")
    da = da.assign_coords(band=band_names)
    return da, band_names


def load_dem(
    stac_api_url: str,
    collections: List[str],
    aoi_geojson: Dict,
    cache_dir: str,
    cache_enabled: bool = True,
) -> xr.DataArray:
    # Known DEM collections commonly available via STAC:
    # - cop-dem-glo-30 (Copernicus DEM GLO-30)
    # - nasa-dem
    # - srtm
    client = Client.open(stac_api_url)
    geom = aoi_geojson.get("geometry", aoi_geojson)
    for col in collections:
        try:
            search = client.search(collections=[col], intersects=geom, max_items=5)
            items = list(search.items())
            if not items:
                continue
            item = _sign_item(items[0], stac_api_url)
            # common asset keys: data, dem, elevation
            for key in ["data", "dem", "elevation", "DSM", "dtm"]:
                if key in item.assets:
                    href = item.assets[key].href
                    if cache_dir:
                        href = _localize_asset(href, cache_dir, cache_enabled)
                    da = rxr.open_rasterio(href, masked=True).squeeze()
                    da = da.rio.clip([shape(geom)], crs="EPSG:4326", drop=True)
                    return da
        except Exception:
            continue
    raise RuntimeError("No DEM items found for AOI")
