from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel, Field

class RunCreate(BaseModel):
    aoi_geojson: Dict[str, Any]
    mode: Literal["coastal", "hardrock"]
    params: Optional[Dict[str, Any]] = None
    geology_geojson: Optional[Dict[str, Any]] = None

class RunResponse(BaseModel):
    run_id: str

class RunItem(BaseModel):
    id: str
    created_at: str
    status: str
    mode: str
    aoi_name: Optional[str] = None
    bbox: Optional[Dict[str, Any]] = None

class RunDetail(BaseModel):
    id: str
    created_at: str
    status: str
    mode: str
    aoi_name: Optional[str] = None
    aoi_geojson: Dict[str, Any]
    bbox: Optional[Dict[str, Any]] = None
    params: Optional[Dict[str, Any]] = None
    progress: Optional[Dict[str, Any]] = None
    overlay_bbox: Optional[Dict[str, Any]] = None
    overlay_path: Optional[str] = None
    sentinel_preview_path: Optional[str] = None
    hillshade_path: Optional[str] = None
    report_path: Optional[str] = None
    error: Optional[str] = None
