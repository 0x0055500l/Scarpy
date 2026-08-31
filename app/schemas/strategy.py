import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ActionStrategy(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    domain: str
    path_pattern: str
    objective: str
    action_type: str
    strategy_type: str = "css"
    selector: str
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: datetime = Field(default_factory=datetime.utcnow)

    def update_confidence(self) -> None:
        total = self.success_count + self.failure_count
        if total == 0:
            self.confidence = 0.0
        else:
            self.confidence = self.success_count / total
