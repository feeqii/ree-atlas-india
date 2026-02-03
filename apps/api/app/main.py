import json
import os
import uuid
from typing import Dict

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from .db import init_db, create_run, update_run, list_runs, get_run, get_targets_geojson, get_target_detail
from .schemas import RunCreate, RunResponse
from .pipeline.utils import aoi_area_km2, aoi_bounds, safe_json_dump
from .settings import settings
from .tasks import process_run

app = FastAPI(title="REE Atlas India API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] ,
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"] ,
)


def _progress_template():
    return {
        "steps": {
            "fetch_imagery": "pending",
            "fetch_dem": "pending",
            "fetch_osm": "pending",
            "compute_features": "pending",
            "score": "pending",
            "extract_targets": "pending",
            "generate_outputs": "pending",
        }
    }


def _update_progress(run_id: str, step: str):
    run = get_run(run_id)
    if not run:
        return
    progress = run.get("progress") or _progress_template()
    if "steps" not in progress:
        progress["steps"] = _progress_template()["steps"]
    for k in progress["steps"].keys():
        if k == step:
            progress["steps"][k] = "running"
        elif progress["steps"][k] == "running":
            progress["steps"][k] = "done"
    update_run(run_id, progress=progress)


def _normalize_aoi(aoi_geojson: Dict) -> Dict:
    if aoi_geojson.get("type") == "FeatureCollection":
        features = aoi_geojson.get("features", [])
        if not features:
            raise HTTPException(status_code=400, detail="AOI FeatureCollection has no features")
        geom = features[0].get("geometry")
        if not geom:
            raise HTTPException(status_code=400, detail="AOI feature missing geometry")
        return {"type": "Feature", "geometry": geom, "properties": features[0].get("properties", {})}
    if aoi_geojson.get("type") == "Feature":
        return aoi_geojson
    # assume geometry
    return {"type": "Feature", "geometry": aoi_geojson, "properties": {}}


@app.on_event("startup")
def startup_event():
    init_db()


@app.post("/runs", response_model=RunResponse)
def create_run_endpoint(run: RunCreate, background_tasks: BackgroundTasks):
    aoi = _normalize_aoi(run.aoi_geojson)
    area_km2 = aoi_area_km2(aoi)
    if area_km2 > settings.max_aoi_km2:
        raise HTTPException(status_code=400, detail=f"AOI too large: {area_km2:.1f} km² > {settings.max_aoi_km2} km²")

    run_id = str(uuid.uuid4())
    bbox = aoi_bounds(aoi)
    run_record = {
        "id": run_id,
        "status": "queued",
        "mode": run.mode,
        "aoi_name": (aoi.get("properties") or {}).get("name"),
        "aoi_geojson": aoi,
        "bbox": {"minx": bbox[0], "miny": bbox[1], "maxx": bbox[2], "maxy": bbox[3]},
        "params": run.params or {},
        "progress": _progress_template(),
    }
    create_run(run_record)

    if settings.enable_async_queue:
        from redis import Redis
        from rq import Queue
        q = Queue("runs", connection=Redis.from_url(settings.redis_url))
        q.enqueue(process_run, run_id, aoi, run.mode, run.params or {}, run.geology_geojson)
    else:
        background_tasks.add_task(process_run, run_id, aoi, run.mode, run.params or {}, run.geology_geojson)
    return {"run_id": run_id}


@app.get("/runs")
def list_runs_endpoint():
    return list_runs()


@app.get("/runs/{run_id}")
def get_run_endpoint(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/runs/{run_id}/targets")
def get_targets_endpoint(run_id: str):
    return get_targets_geojson(run_id)


@app.get("/runs/{run_id}/targets/{target_id}")
def get_target_detail_endpoint(run_id: str, target_id: str):
    target = get_target_detail(run_id, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


@app.get("/runs/{run_id}/overlay.png")
def overlay_endpoint(run_id: str):
    run = get_run(run_id)
    if not run or not run.get("overlay_path"):
        raise HTTPException(status_code=404, detail="Overlay not found")
    return FileResponse(run["overlay_path"], media_type="image/png")

@app.get("/runs/{run_id}/sentinel.png")
def sentinel_endpoint(run_id: str):
    run = get_run(run_id)
    if not run or not run.get("sentinel_preview_path"):
        raise HTTPException(status_code=404, detail="Sentinel preview not found")
    return FileResponse(run["sentinel_preview_path"], media_type="image/png")


@app.get("/runs/{run_id}/hillshade.png")
def hillshade_endpoint(run_id: str):
    run = get_run(run_id)
    if not run or not run.get("hillshade_path"):
        raise HTTPException(status_code=404, detail="Hillshade not found")
    return FileResponse(run["hillshade_path"], media_type="image/png")


@app.get("/runs/{run_id}/report.html")
def report_endpoint(run_id: str):
    run = get_run(run_id)
    if not run or not run.get("report_path"):
        raise HTTPException(status_code=404, detail="Report not found")
    return HTMLResponse(open(run["report_path"], "r", encoding="utf-8").read())


@app.get("/runs/{run_id}/exports/targets.geojson")
def targets_geojson_export(run_id: str):
    path = os.path.join(settings.data_dir, "runs", run_id, "targets.geojson")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="targets.geojson not found")
    return FileResponse(path, media_type="application/geo+json")


@app.get("/runs/{run_id}/exports/targets.csv")
def targets_csv_export(run_id: str):
    path = os.path.join(settings.data_dir, "runs", run_id, "targets.csv")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="targets.csv not found")
    return FileResponse(path, media_type="text/csv")


@app.get("/runs/{run_id}/exports/roads.geojson")
def roads_geojson_export(run_id: str):
    path = os.path.join(settings.data_dir, "runs", run_id, "roads.geojson")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="roads.geojson not found")
    return FileResponse(path, media_type="application/geo+json")


@app.get("/runs/{run_id}/exports/rivers.geojson")
def rivers_geojson_export(run_id: str):
    path = os.path.join(settings.data_dir, "runs", run_id, "rivers.geojson")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="rivers.geojson not found")
    return FileResponse(path, media_type="application/geo+json")


@app.get("/runs/{run_id}/exports/coast.geojson")
def coast_geojson_export(run_id: str):
    path = os.path.join(settings.data_dir, "runs", run_id, "coast.geojson")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="coast.geojson not found")
    return FileResponse(path, media_type="application/geo+json")


@app.post("/uploads/geology")
def upload_geology(run_id: str, geology_geojson: Dict):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run_dir = os.path.join(settings.data_dir, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    safe_json_dump(geology_geojson, os.path.join(run_dir, "geology.geojson"))
    update_run(run_id, params={"input": run.get("params", {}), "geology_uploaded": True})
    return {"status": "ok"}
