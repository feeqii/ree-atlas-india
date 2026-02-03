import numpy as np
import xarray as xr
import rioxarray  # noqa: F401
from affine import Affine

from app.pipeline.targets import extract_targets, evidence_chips


def make_da(data):
    da = xr.DataArray(data, dims=("y", "x"))
    da.rio.write_crs("EPSG:4326", inplace=True)
    transform = Affine.translation(77.0, 28.0) * Affine.scale(0.01, -0.01)
    da.rio.write_transform(transform, inplace=True)
    return da


def test_extract_targets_min_area_filters():
    data = np.zeros((10, 10), dtype="float32")
    data[0:2, 0:2] = 0.95
    score_da = make_da(data)

    targets = extract_targets(
        score_da,
        threshold=0.9,
        min_area_km2=10.0,
        mode="coastal",
        evidence_layers={"ndvi": score_da, "ndwi": score_da, "bsi": score_da, "slope": score_da,
                         "dist_coast": score_da, "dist_river": score_da},
        thresholds={"slope_max": 5, "ndvi_max": 0.2, "bsi_threshold_value": 0.5, "coast_max_m": 30000, "river_max_m": 10000},
        roads_gdf=None,
        rivers_gdf=None,
    )
    assert len(targets) == 0


def test_evidence_chips_deterministic():
    evidence = {
        "pct_near_coast": 0.8,
        "pct_low_slope": 0.6,
        "pct_low_ndvi": 0.4,
        "pct_high_bsi": 0.9,
        "pct_near_river": 0.1,
    }
    chips = evidence_chips(evidence, mode="coastal")
    assert chips[0] == "High sandiness (BSI top 30%)"
    assert "Near coastline (<30 km)" in chips
