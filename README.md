# REE Atlas India

REE Atlas India is a production-quality MVP that turns open satellite, terrain and map signals into an **explainable prospectivity map** and **ranked target list** for rare‑earth exploration in India. It is intentionally transparent (no ML in v1) and designed to help field teams prioritize targets for validation.

**What it is**
- A local, self‑hosted app that ingests open data (Sentinel‑2, DEM, OSM) and produces a reproducible scoring output with evidence.
- Two modes: Coastal Placer (monazite‑heavy mineral sands proxy) and Hard‑Rock (carbonatite/alkaline/structural proxy).

**What it is not**
- It does not confirm deposits or replace geological fieldwork.
- It is not a regulatory or financial decision tool.

## Quickstart

```bash
cd ree-atlas-india
cp infra/.env.example infra/.env

docker compose up --build
```

Open:
- Web app: http://localhost:3000
- API docs: http://localhost:8000/docs

## One‑command dev

```bash
docker compose up --build
```

Optional async queue (RQ + Redis):

```bash
docker compose --profile async up --build
```

## Tech Stack
- Frontend: Next.js (App Router, TypeScript), MapLibre GL JS, Tailwind
- Backend: FastAPI + PostGIS
- Geospatial: rasterio, rioxarray/xarray, shapely, geopandas, pyproj
- STAC: pystac-client (+ planetary-computer auth helper)
- OSM: Overpass API

## Data Sources & Attribution
- Sentinel‑2 L2A (Copernicus): https://sentinels.copernicus.eu/web/sentinel/user-guides/sentinel-2-msi
- Copernicus DEM GLO‑30: https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model
- OpenStreetMap (ODbL): https://www.openstreetmap.org/copyright
- STAC endpoint (default): https://planetarycomputer.microsoft.com/

These are also listed in the in‑app **Data Sources** page.

## How Scoring Works

### Sentinel indices
- **NDVI** = (NIR − RED) / (NIR + RED)
- **NDWI** = (GREEN − NIR) / (GREEN + NIR)
- **BSI** = ((SWIR + RED) − (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))

Sentinel‑2 bands:
- BLUE=B2, GREEN=B3, RED=B4, NIR=B8, SWIR=B11

### Coastal Placer mode
High score when:
- **Near coastline** (default 0–30 km)
- **Low slope** (<= 5°)
- **Low NDVI** (<= 0.2)
- **High BSI** (top 30% within AOI)
- **Not water** (NDWI < 0.1)
- Optional: **Near rivers** (default 0–10 km)

Weights (defaults):
- coastal_proximity 0.30
- slope 0.20
- bare_land 0.20
- sandiness 0.20
- river_proximity 0.10

### Hard‑Rock mode
High score when:
- **High lineament density** (top 30%)
- **Moderate relief** (slope 2–25°)
- **Low vegetation cover** (NDVI <= 0.4)
- Optional geology boost (if uploaded lithology matches keywords)

Weights (defaults):
- lineaments 0.45
- relief 0.20
- exposure 0.20
- geology_boost 0.15 (if geology present else redistributed)

### Explainability
Each target stores:
- Weights + thresholds used
- Mean feature values in polygon
- % of polygon meeting each threshold
- Deterministic top‑3 reason chips

## Outputs
For each run:
- `targets.geojson`
- `targets.csv`
- `report.html`
- `overlay.png`, `sentinel_preview.png`, `dem_hillshade.png`

## API Endpoints
- `POST /runs` → start a run
- `GET /runs` → list run history
- `GET /runs/{run_id}` → run status + metadata
- `GET /runs/{run_id}/targets` → target GeoJSON
- `GET /runs/{run_id}/overlay.png`
- `GET /runs/{run_id}/sentinel.png`
- `GET /runs/{run_id}/hillshade.png`
- `GET /runs/{run_id}/report.html`
- `GET /runs/{run_id}/exports/targets.geojson`
- `GET /runs/{run_id}/exports/targets.csv`
- `POST /uploads/geology` → upload optional lithology polygons

## Environment Variables
See `infra/.env.example`:
- `DATABASE_URL`
- `STAC_API_URL`
- `STAC_COLLECTION_S2`
- `STAC_COLLECTION_DEM`
- `MAX_AOI_KM2`
- `ENABLE_ASYNC_QUEUE`
- `REDIS_URL`
- `NEXT_PUBLIC_API_URL`

## Useful Run Parameters (optional)
These can be passed in the `params` object of `POST /runs`:
- `max_items` (int): limit Sentinel items (default 3)
- `cache_downloads` (bool): cache STAC assets to disk (default false)
- `osm_timeout_s` (int): Overpass timeout seconds (default 40)
- `use_synthetic` (bool): **testing only** synthetic data pipeline
- `synthetic_width` / `synthetic_height` (int): synthetic grid size

## Limitations & Safety
- AOI size is limited (default 2,500 km²) to keep runs fast.
- If a DEM STAC collection is unavailable, the pipeline falls back to a flat DEM.
- Overpass can be rate‑limited; road/river distances may be empty in that case.
- **This tool does not confirm a deposit** and must be validated by field work.

## Roadmap (v2 ideas)
- Radiometrics / geophysics ingestion
- Improved lineament extraction + multi‑scale analysis
- ML‑based prospectivity with strict explainability
- Offline tiles + cached STAC catalogs
- Multi‑user auth + saved projects

## Development Notes
- Backend tests: `pytest`
- Formatting: `ruff` + `black`

## Documentation

- `docs/DEVELOPMENT.md`: local dev, configuration, troubleshooting
- `docs/ARCHITECTURE.md`: system overview and pipeline internals

---

Built with open data and open‑source software.
