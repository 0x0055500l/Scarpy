from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class BaseORMModel(BaseModel):
    """Base Pydantic model with ORM mode enabled."""
    model_config = ConfigDict(from_attributes=True)

class JobCreate(BaseModel):
    """Request model for creating a new extraction job."""
    url: str = Field(..., description="The target URL to process.")
    objective: str = Field(
        ..., description="The information to extract or goal to achieve."
    )
    schema_definition: Optional[Dict[str, Any]] = Field(
        None, description="Optional JSON Schema defining the exact output format."
    )

class JobResponse(BaseORMModel):
    """Response model for a job."""
    id: str
    url: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
