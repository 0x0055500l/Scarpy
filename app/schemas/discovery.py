from typing import Any, List, Optional

from pydantic import BaseModel, Field


class DiscoveryLimits(BaseModel):
    max_pages: int = Field(default=10, description="Maximum number of pages to visit")
    max_depth: int = Field(default=3, description="Maximum crawl depth from the start URL")
    max_actions: int = Field(default=50, description="Maximum number of actions per page")
    max_execution_time_seconds: int = Field(default=600, description="Maximum execution time in seconds")
    target_domain: Optional[str] = Field(default=None, description="Domain to restrict the crawl to")

class DiscoveryMetadata(BaseModel):
    start_time: str
    end_time: str
    duration_seconds: float
    pages_visited_count: int

class DiscoveryResult(BaseModel):
    data: List[Any] = Field(default_factory=list, description="Extracted data")
    metadata: Optional[DiscoveryMetadata] = None
    pages_visited: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
