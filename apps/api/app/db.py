from contextlib import contextmanager
import json
import psycopg2
from psycopg2 import pool
from psycopg2.extras import Json
from .settings import settings

_pool = None


def init_db():
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(1, 5, settings.database_url)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id UUID PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    aoi_name TEXT,
                    aoi_geojson JSONB NOT NULL,
                    aoi_geom geometry(Polygon, 4326),
                    bbox JSONB,
                    params JSONB,
                    progress JSONB,
                    overlay_path TEXT,
                    overlay_bbox JSONB,
                    sentinel_preview_path TEXT,
                    hillshade_path TEXT,
                    report_path TEXT,
                    error TEXT
                );
                """
            )
            cur.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS aoi_name TEXT;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS targets (
                    id UUID PRIMARY KEY,
                    run_id UUID REFERENCES runs(id) ON DELETE CASCADE,
                    geom geometry(Polygon, 4326),
                    area_km2 DOUBLE PRECISION,
                    centroid geometry(Point, 4326),
                    mean_score DOUBLE PRECISION,
                    max_score DOUBLE PRECISION,
                    distance_to_road_m DOUBLE PRECISION,
                    distance_to_river_m DOUBLE PRECISION,
                    evidence JSONB,
                    evidence_summary JSONB
                );
                """
            )
        conn.commit()


@contextmanager
def get_conn():
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(1, 5, settings.database_url)
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


def create_run(run):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs (id, status, mode, aoi_name, aoi_geojson, aoi_geom, bbox, params, progress)
                VALUES (%s, %s, %s, %s, %s, ST_GeomFromGeoJSON(%s), %s, %s, %s)
                """,
                (
                    run["id"],
                    run["status"],
                    run["mode"],
                    run.get("aoi_name"),
                    Json(run["aoi_geojson"]),
                    json.dumps(run["aoi_geojson"]["geometry"]) if "geometry" in run["aoi_geojson"] else json.dumps(run["aoi_geojson"]),
                    Json(run.get("bbox")),
                    Json(run.get("params")),
                    Json(run.get("progress")),
                ),
            )
        conn.commit()


def update_run(run_id, **fields):
    if not fields:
        return
    cols = []
    vals = []
    for k, v in fields.items():
        cols.append(f"{k} = %s")
        if isinstance(v, (dict, list)):
            vals.append(Json(v))
        else:
            vals.append(v)
    vals.append(run_id)
    sql = f"UPDATE runs SET {', '.join(cols)} WHERE id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, vals)
        conn.commit()


def insert_targets(run_id, targets):
    with get_conn() as conn:
        with conn.cursor() as cur:
            for t in targets:
                cur.execute(
                    """
                    INSERT INTO targets (id, run_id, geom, area_km2, centroid, mean_score, max_score,
                                         distance_to_road_m, distance_to_river_m, evidence, evidence_summary)
                    VALUES (%s, %s, ST_GeomFromText(%s, 4326), %s, ST_GeomFromText(%s, 4326), %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        t["id"],
                        run_id,
                        t["wkt"],
                        t["area_km2"],
                        t["centroid_wkt"],
                        t["mean_score"],
                        t["max_score"],
                        t.get("distance_to_road_m"),
                        t.get("distance_to_river_m"),
                        Json(t.get("evidence")),
                        Json(t.get("evidence_summary")),
                    ),
                )
        conn.commit()


def list_runs():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, status, mode, aoi_name, bbox
                FROM runs
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()
    return [
        {
            "id": str(r[0]),
            "created_at": r[1].isoformat(),
            "status": r[2],
            "mode": r[3],
            "aoi_name": r[4],
            "bbox": r[5],
        }
        for r in rows
    ]


def get_run(run_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, status, mode, aoi_name, aoi_geojson, bbox, params, progress,
                       overlay_bbox, overlay_path, sentinel_preview_path, hillshade_path, report_path, error
                FROM runs WHERE id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "created_at": row[1].isoformat(),
        "status": row[2],
        "mode": row[3],
        "aoi_name": row[4],
        "aoi_geojson": row[5],
        "bbox": row[6],
        "params": row[7],
        "progress": row[8],
        "overlay_bbox": row[9],
        "overlay_path": row[10],
        "sentinel_preview_path": row[11],
        "hillshade_path": row[12],
        "report_path": row[13],
        "error": row[14],
    }


def get_targets_geojson(run_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ST_AsGeoJSON(geom), area_km2, mean_score, max_score, distance_to_road_m,
                       distance_to_river_m, evidence_summary
                FROM targets WHERE run_id = %s
                ORDER BY mean_score DESC, area_km2 DESC
                """,
                (run_id,),
            )
            rows = cur.fetchall()
    features = []
    for r in rows:
        features.append(
            {
                "type": "Feature",
                "geometry": json.loads(r[1]),
                "properties": {
                    "id": str(r[0]),
                    "area_km2": r[2],
                    "mean_score": r[3],
                    "max_score": r[4],
                    "distance_to_road_m": r[5],
                    "distance_to_river_m": r[6],
                    "evidence_summary": r[7] or [],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def get_target_detail(run_id, target_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ST_AsGeoJSON(geom), area_km2, mean_score, max_score, distance_to_road_m,
                       distance_to_river_m, evidence
                FROM targets WHERE run_id = %s AND id = %s
                """,
                (run_id, target_id),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "geometry": json.loads(row[1]),
        "area_km2": row[2],
        "mean_score": row[3],
        "max_score": row[4],
        "distance_to_road_m": row[5],
        "distance_to_river_m": row[6],
        "evidence": row[7] or {},
    }
