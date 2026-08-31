import pytest

from app.core.exceptions import AgentBaseError, NavigationError


def test_exception_inheritance() -> None:
    """Test that custom exceptions inherit from the base class."""
    with pytest.raises(AgentBaseError):
        raise NavigationError("Could not reach the site.")
