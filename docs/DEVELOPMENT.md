# Development

This repo is designed to run locally via Docker Compose (recommended). The stack is:

- `db`: Postgres + PostGIS
- `api`: FastAPI service that runs the geospatial pipeline
- `web`: Next.js app (MapLibre-based UI)
- Optional: `redis` + `worker` for async run processing (RQ)

## Quickstart (Docker Compose)

From the repo root:

```bash
cp infra/.env.example infra/.env
docker compose up --build
```

Open:

- Web: `http://localhost:3000`
- API (Swagger): `http://localhost:8000/docs`

## Async Queue (Optional)

To run the async profile (Redis + RQ worker):

```bash
docker compose --profile async up --build
```

Notes:

- The API decides between synchronous vs queued execution via `ENABLE_ASYNC_QUEUE`.
- The `worker` runs `rq worker runs`.

## Common Tasks

### Rebuild a Single Service

```bash
docker compose build api
docker compose up api
```

### Reset the Database

This removes the Postgres volume and re-creates tables on API startup.

```bash
docker compose down -v
docker compose up --build
```

### Where Outputs Go

The API writes artifacts under `DATA_DIR` (default `./data` mounted to `/app/data`):

- `data/runs/<run_id>/`: run outputs and exports
- `data/cache/`: optional cached STAC downloads (if enabled)

## Tests

Backend tests live under `apps/api/tests`.

Option 1: run tests inside the API container:

```bash
docker compose exec api pytest
```

Option 2: run tests locally (outside Docker):

- Requires a local Python 3.11 environment and geospatial dependencies.
- This path is not the “happy path”; Compose is the supported default.

## Configuration

Configuration is primarily environment-variable driven.

- Local defaults live in `infra/.env.example`.
- Compose loads `infra/.env` via `env_file`.

Key variables:

- `DATABASE_URL`: Postgres connection string used by the API
- `DATA_DIR`: where runs and cache are written (in-container path)
- `STAC_API_URL`: STAC endpoint (default points at Planetary Computer)
- `STAC_COLLECTION_S2`: Sentinel-2 collection name
- `STAC_COLLECTION_DEM`: DEM collection(s), comma-separated
- `MAX_AOI_KM2`: server-side AOI size limit
- `ENABLE_ASYNC_QUEUE`: `true` to enqueue with RQ, otherwise uses FastAPI background tasks
- `REDIS_URL`: Redis connection URL (only relevant for async mode)
- `NEXT_PUBLIC_API_URL`: Web frontend API base URL

## Useful Run Parameters

These are sent by the frontend in the `params` object of `POST /runs`.

- `time_range`: STAC datetime range (defaults to last 365 days)
- `cloud_cover_max`: filter Sentinel items by `eo:cloud_cover` (default 40)
- `max_items`: number of Sentinel items used for the composite (default 3)
- `cache_downloads`: if `true`, downloads STAC assets to `data/cache/`
- `osm_timeout_s`: Overpass timeout in seconds (default 40)
- `threshold_method`: `percentile` or `fixed`
- `target_percentile`: percentile threshold for target extraction (default 95)
- `fixed_threshold`: fixed score threshold (default 0.7)
- `min_area_km2`: minimum target polygon area (default 0.1)

### Synthetic Mode (Testing)

Synthetic mode avoids external calls and produces deterministic “toy” rasters.

- `use_synthetic`: `true`
- `synthetic_width` / `synthetic_height`: grid size

This is useful for debugging UI and pipeline flow without STAC/Overpass variability.

