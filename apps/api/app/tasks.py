from typing import Dict, Optional

from .db import update_run, insert_targets
from .pipeline.run import run_pipeline


def process_run(run_id: str, aoi: Dict, mode: str, params: Dict, geology_geojson: Optional[Dict] = None):
    def progress_cb(step):
        from .main import _update_progress
        _update_progress(run_id, step)

    try:
        update_run(run_id, status="running")
        result = run_pipeline(run_id, aoi, mode, params or {}, geology_geojson, progress_cb=progress_cb)
        targets = result["targets"]
        insert_targets(
            run_id,
            [
                {
                    "id": t["id"],
                    "wkt": t["geometry"].wkt,
                    "centroid_wkt": t["centroid"].wkt,
                    "area_km2": t["area_km2"],
                    "mean_score": t["mean_score"],
                    "max_score": t["max_score"],
                    "distance_to_road_m": t["distance_to_road_m"],
                    "distance_to_river_m": t["distance_to_river_m"],
                    "evidence": t["evidence"],
                    "evidence_summary": t["evidence_summary"],
                }
                for t in targets
            ],
        )
        progress = {"steps": {}}
        for step in ["fetch_imagery", "fetch_dem", "fetch_osm", "compute_features", "score", "extract_targets", "generate_outputs"]:
            progress["steps"][step] = "done"
        update_run(
            run_id,
            status="completed",
            overlay_path=result["overlay_path"],
            overlay_bbox=result["overlay_bbox"],
            sentinel_preview_path=result["sentinel_preview_path"],
            hillshade_path=result["hillshade_path"],
            report_path=result["report_path"],
            params={"input": params or {}, "score_meta": result["score_meta"]},
            progress=progress,
        )
    except Exception as e:
        update_run(run_id, status="failed", error=str(e))
