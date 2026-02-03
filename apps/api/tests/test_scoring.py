import numpy as np
import xarray as xr

from app.pipeline.scoring import _percentile_scale, coastal_score


def test_percentile_scale_bounds():
    data = np.array([[0, 1], [2, 3]], dtype="float32")
    da = xr.DataArray(data)
    scaled = _percentile_scale(da, 0, 100)
    assert float(scaled.min()) == 0.0
    assert float(scaled.max()) == 1.0


def test_coastal_water_mask_zero():
    arr = xr.DataArray(np.ones((2, 2), dtype="float32"))
    score, meta = coastal_score(
        ndvi=arr * 0.1,
        ndwi=arr * 0.5,
        bsi=arr * 0.2,
        slope=arr * 1.0,
        dist_coast_m=arr * 1000,
        dist_river_m=arr * 1000,
        params={"ndwi_water_max": 0.1}
    )
    assert float(score.max()) == 0.0
