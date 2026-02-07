# Architecture

REE Atlas India is a local, self-hosted application that turns open geospatial signals into a scored raster, extracted target polygons, and an HTML report. The system is intentionally deterministic and explainable (no ML in v1).

## Services

Docker Compose runs these services:

- `db` (`postgis/postgis`): stores run metadata and extracted target summaries
- `api` (FastAPI): orchestrates the pipeline and exposes REST endpoints
- `web` (Next.js): UI for drawing an AOI, starting runs, and viewing outputs
- Optional `redis` + `worker`: async run execution via RQ

## Request Flow

1. The user draws an AOI in the web UI (a GeoJSON polygon).
2. The web UI calls `POST /runs` with:
   - `aoi_geojson`
   - `mode`: `coastal` or `hardrock`
   - optional `params` and `geology_geojson`
3. The API stores a `runs` row, then processes the run:
   - synchronously via FastAPI background tasks, or
   - asynchronously via RQ (if `ENABLE_ASYNC_QUEUE=true`)
4. The API writes artifacts under `DATA_DIR/runs/<run_id>/` and stores pointers on the run record.
5. When complete, the UI polls `GET /runs/{run_id}` then fetches targets via `GET /runs/{run_id}/targets`.

## Run Lifecycle

Runs are stored in Postgres table `runs` with:

- `status`: `queued` | `running` | `completed` | `failed`
- `progress`: a step map that the UI can display
- `aoi_geojson` and `aoi_geom` (PostGIS geometry)
- output paths and error info

Extracted targets are stored in `targets`:

- geometry and centroid (PostGIS)
- score summary (`mean_score`, `max_score`)
- distance-to-road/river (meters, computed in UTM)
- explainability fields (`evidence`, `evidence_summary`)

## Pipeline Steps

The main pipeline lives in `apps/api/app/pipeline/run.py`.

Step sequence (mirrors `progress.steps`):

1. `fetch_imagery`
   - Search STAC for Sentinel-2 items within AOI/time range
   - Build a median composite for bands `B2,B3,B4,B8,B11`
   - Compute indices: NDVI, NDWI, BSI
2. `fetch_dem`
   - Load a DEM via STAC (tries multiple configured collections)
   - Compute slope and hillshade
   - Falls back to a flat DEM if unavailable
3. `fetch_osm`
   - Query Overpass for roads, rivers, and coastline within AOI bounds
   - Compute distance-to-line rasters
4. `compute_features`
   - Hard-rock mode: compute a lineament-density raster from hillshade
   - Optional: rasterize uploaded geology polygons into a mask
5. `score`
   - `coastal`: combines coastal proximity, slope, bare land, sandiness, river proximity
   - `hardrock`: combines lineaments, relief, exposure, optional geology boost
   - Applies a water mask using NDWI
6. `extract_targets`
   - Thresholds the score raster (percentile or fixed)
   - Removes small blobs, polygonizes, and computes per-target evidence
7. `generate_outputs`
   - Renders images and exports: overlay, previews, `targets.geojson`, `targets.csv`, `report.html`

## Data and File Outputs

Per-run directory (relative to `DATA_DIR`):

- `runs/<run_id>/sentinel_composite.tif`
- `runs/<run_id>/{ndvi,ndwi,bsi}.tif`
- `runs/<run_id>/{dem,slope,hillshade}.tif`
- `runs/<run_id>/score.tif`
- `runs/<run_id>/{roads,rivers,coast}.geojson`
- `runs/<run_id>/{dist_roads,dist_rivers,dist_coast}.tif`
- `runs/<run_id>/overlay.png`
- `runs/<run_id>/sentinel_preview.png`
- `runs/<run_id>/dem_hillshade.png`
- `runs/<run_id>/targets.geojson`
- `runs/<run_id>/targets.csv`
- `runs/<run_id>/report.html`
- `runs/<run_id>/score_meta.json`
- `runs/<run_id>/geology.geojson` (only if uploaded)

## Explainability Model

Each extracted target stores:

- mean values for key layers within the polygon
- percent-of-polygon meeting each threshold
- a deterministic top-3 “reason chip” list derived from evidence percentages

The goal is that each target is auditable: scores can be traced back to threshold and layer behavior inside the AOI.

