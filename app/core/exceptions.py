class AgentBaseError(Exception):
    """Base exception for all Web Discovery Agent errors."""
    pass

class ConfigurationError(AgentBaseError):
    """Raised when there is a configuration issue."""
    pass

class BrowserError(AgentBaseError):
    """Raised when there is an issue with the browser instance."""
    pass

class NavigationError(BrowserError):
    """Raised when navigation to a URL fails."""
    pass

class ActionError(AgentBaseError):
    """Raised when an interaction with a web element fails."""
    pass

class ExtractionError(AgentBaseError):
    """Raised when data extraction from the DOM fails."""
    pass

class AgentError(AgentBaseError):
    """Raised when the AI engine fails to reason or return valid structured output."""
    pass

class AuthenticationError(AgentBaseError):
    """Raised when authentication on a target site fails."""
    pass

class RecoveryError(AgentBaseError):
    """Raised when error recovery strategies fail."""
    pass
