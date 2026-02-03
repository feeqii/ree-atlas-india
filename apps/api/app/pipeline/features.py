from typing import Tuple

import numpy as np
import rioxarray as rxr
import xarray as xr
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt
from shapely.geometry import shape

from .utils import normalize_minmax


def compute_indices(s2_da: xr.DataArray) -> Tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    band_map = {b: i for i, b in enumerate(s2_da.band.values)}
    blue = s2_da.isel(band=band_map["B2"]).astype("float32")
    green = s2_da.isel(band=band_map["B3"]).astype("float32")
    red = s2_da.isel(band=band_map["B4"]).astype("float32")
    nir = s2_da.isel(band=band_map["B8"]).astype("float32")
    swir = s2_da.isel(band=band_map["B11"]).astype("float32")

    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir - red) / (nir + red)
        ndwi = (green - nir) / (green + nir)
        bsi = ((swir + red) - (nir + blue)) / ((swir + red) + (nir + blue))

    return ndvi, ndwi, bsi


def distance_raster(lines_gdf, ref_da: xr.DataArray) -> xr.DataArray:
    shape_hw = (ref_da.shape[-2], ref_da.shape[-1])
    transform = ref_da.rio.transform()
    crs = ref_da.rio.crs
    if crs is None:
        data = np.full(shape_hw, 1e6, dtype="float32")
        return ref_da.copy(data=data)
    if lines_gdf is None or lines_gdf.empty:
        data = np.full(shape_hw, 1e6, dtype="float32")
        return ref_da.copy(data=data)

    gdf_proj = lines_gdf.to_crs(crs)
    shapes = [(geom, 1) for geom in gdf_proj.geometry if geom is not None and not geom.is_empty]
    if not shapes:
        data = np.full(shape_hw, 1e6, dtype="float32")
        return ref_da.copy(data=data)

    raster = rasterize(
        shapes,
        out_shape=shape_hw,
        transform=transform,
        fill=0,
        dtype="uint8",
    )
    # distance in pixels
    dist_px = distance_transform_edt(1 - raster)
    xres, yres = ref_da.rio.resolution()
    dist_m = dist_px * float(abs(xres))
    return ref_da.copy(data=dist_m)


def lineament_density(hillshade_da: xr.DataArray) -> xr.DataArray:
    from skimage.feature import canny
    from skimage.morphology import skeletonize
    from scipy.ndimage import uniform_filter

    img = hillshade_da.values.astype("float32")
    # Normalize
    img = normalize_minmax(img)
    edges = canny(img, sigma=2)
    skel = skeletonize(edges).astype("float32")
    density = uniform_filter(skel, size=15)
    density = normalize_minmax(density)
    return hillshade_da.copy(data=density)
