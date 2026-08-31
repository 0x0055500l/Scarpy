from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, SecretStr


class AuthCredentials(BaseModel):
    username: str
    password: SecretStr

class AgentStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    NAVIGATING = "NAVIGATING"
    OBSERVING = "OBSERVING"
    ACTING = "ACTING"
    VERIFYING = "VERIFYING"
    EXTRACTING = "EXTRACTING"
    RECOVERING = "RECOVERING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class StepPlan(BaseModel):
    id: str
    action_type: str = Field(description="e.g. navigate, click, fill, extract, verify")
    description: str = Field(description="Natural language description of the step")
    target: Optional[str] = Field(None, description="CSS selector or conceptual target")
    value: Optional[str] = Field(None, description="Value to fill if applicable")

class ActionRecord(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    step_id: str
    action: str
    target: Optional[str] = None
    success: bool
    duration_ms: float = 0.0
    error: Optional[str] = None

class ObservationRecord(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    step_id: str
    url: str
    elements: List[str]
    context_summary: str = ""

class VerificationRecord(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    step_id: str
    success: bool
    reason: str = ""

class AgentState(BaseModel):
    task_id: str
    session_id: str
    goal: str
    current_url: str = ""
    current_step_index: int = 0
    plan: List[StepPlan] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.CREATED
    visited_urls: set[str] = Field(default_factory=set)
    actions: List[ActionRecord] = Field(default_factory=list)
    observations: List[ObservationRecord] = Field(default_factory=list)
    verifications: List[VerificationRecord] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    recovery_attempts: int = 0
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    paused_reason: Optional[str] = None
