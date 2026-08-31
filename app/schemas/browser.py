from typing import Optional

from pydantic import BaseModel


class ActionResult(BaseModel):
    """Result of an action performed in the browser."""
    success: bool
    action: str
    target: Optional[str] = None
    evidence: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None

class ElementObservation(BaseModel):
    """Represents a selectively observed element on the page."""
    tag: str
    text: str
    attributes: dict[str, str]

class PageObservation(BaseModel):
    """Structured observation of the current page state."""
    url: str
    title: str
    interactive_elements: list[ElementObservation]
