import numpy as np
import rioxarray as rxr
from rasterio.enums import Resampling


def compute_slope(dem_da):
    # dem_da in meters, assume projected CRS
    xres, yres = dem_da.rio.resolution()
    dzdx, dzdy = np.gradient(dem_da.values.astype("float32"), xres, yres)
    slope = np.degrees(np.arctan(np.sqrt(dzdx**2 + dzdy**2)))
    return dem_da.copy(data=slope)


def compute_hillshade(dem_da, azimuth=315, altitude=45):
    az = np.radians(azimuth)
    alt = np.radians(altitude)
    xres, yres = dem_da.rio.resolution()
    dzdx, dzdy = np.gradient(dem_da.values.astype("float32"), xres, yres)
    slope = np.pi / 2.0 - np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    aspect = np.arctan2(-dzdx, dzdy)
    shaded = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    shaded = np.clip(shaded, 0, 1)
    return dem_da.copy(data=shaded)


def reproject_to_match(da, ref_da):
    return da.rio.reproject_match(ref_da, resampling=Resampling.bilinear)
