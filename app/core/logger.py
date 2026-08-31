import logging
import sys

import structlog

from app.core.config import settings


def setup_logger() -> None:
    """Configure structured logging for the application."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = logging.Formatter("%(message)s")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger instance."""
    return structlog.get_logger(name) # type: ignore


def bind_task_context(
    logger: structlog.stdlib.BoundLogger,
    task_id: str,
    session_id: str,
    url: str,
    action: str = "init",
    attempt: int = 1,
) -> structlog.stdlib.BoundLogger:
    """Bind task-specific context variables to the logger."""
    return logger.bind(
        task_id=task_id,
        session_id=session_id,
        url=url,
        action=action,
        attempt=attempt
    )
