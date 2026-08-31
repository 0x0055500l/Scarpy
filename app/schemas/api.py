from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, HttpUrl


class TaskCreateRequest(BaseModel):
    url: HttpUrl
    objective: str = Field(..., description="The objective for the agent")
    schema_definition: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional Pydantic schema representation (e.g. {'name': 'str'})"
    )
    options: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional execution settings like {'headed': True, 'verbose': True}"
    )

class TaskResponse(BaseModel):
    id: str
    url: str
    goal: str
    status: str
    created_at: datetime
    error: Optional[str] = None
    options: Optional[Dict[str, Any]] = None

class TaskEventResponse(BaseModel):
    event_type: str
    timestamp: Optional[datetime] = None
    details: Optional[Dict[str, Any]] = None

class TaskResultResponse(BaseModel):
    id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
