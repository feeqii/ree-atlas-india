import os
from dataclasses import dataclass

@dataclass
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://ree:ree@db:5432/ree_atlas")
    data_dir: str = os.getenv("DATA_DIR", "/app/data")
    stac_api_url: str = os.getenv("STAC_API_URL", "https://planetarycomputer.microsoft.com/api/stac/v1")
    stac_collection_s2: str = os.getenv("STAC_COLLECTION_S2", "sentinel-2-l2a")
    stac_collection_dem: str = os.getenv("STAC_COLLECTION_DEM", "cop-dem-glo-30")
    max_aoi_km2: float = float(os.getenv("MAX_AOI_KM2", "2500"))
    enable_async_queue: bool = os.getenv("ENABLE_ASYNC_QUEUE", "false").lower() == "true"
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

settings = Settings()
