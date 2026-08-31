from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete
from sqlalchemy.future import select

from app.core.logger import get_logger
from app.db.models import AgentMemory, ExecutionEvent
from app.db.session import get_db_session

logger = get_logger(__name__)

def _now() -> datetime:
    return datetime.now(timezone.utc)

class HistoryManager:
    """Manages the persistent execution history of the agent."""

    def __init__(self, task_id: str, session_id: str) -> None:
        self.task_id = task_id
        self.session_id = session_id
        # Keys to sanitize from details to prevent secret leakage
        self.sensitive_keys = {"password", "secret", "token", "key", "auth"}

    def _sanitize_details(self, details: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not details:
            return details

        sanitized: Dict[str, Any] = {}
        for k, v in details.items():
            is_sensitive = any(sk in k.lower() for sk in self.sensitive_keys)
            if is_sensitive and v:
                sanitized[k] = "***"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_details(v)
            else:
                sanitized[k] = v
        return sanitized

    async def log_event(self, event_type: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Logs an execution event to the database, sanitizing secrets."""
        sanitized_details = self._sanitize_details(details)

        async with get_db_session() as session:
            event = ExecutionEvent(
                task_id=self.task_id,
                session_id=self.session_id,
                event_type=event_type,
                details=sanitized_details
            )
            session.add(event)
            await session.commit()
            logger.info("Logged execution event", event_type=event_type, session_id=self.session_id)

    async def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent events for the current session."""
        async with get_db_session() as session:
            stmt = select(ExecutionEvent).where(
                ExecutionEvent.session_id == self.session_id
            ).order_by(ExecutionEvent.timestamp.desc()).limit(limit)

            result = await session.execute(stmt)
            events = result.scalars().all()

            return [
                {
                    "event_type": e.event_type,
                    "details": e.details,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None
                }
                for e in events
            ]

    async def set_memory(self, key: str, value: Any) -> None:
        """Stores a key-value pair in long-term semantic memory."""
        async with get_db_session() as session:
            mem = await session.get(AgentMemory, key)
            if mem:
                mem.value = value
            else:
                mem = AgentMemory(key=key, value=value)
                session.add(mem)
            await session.commit()
            logger.info("Updated semantic memory", memory_key=key)

    async def get_memory(self, key: str) -> Optional[Any]:
        """Retrieves a value from long-term semantic memory."""
        async with get_db_session() as session:
            mem = await session.get(AgentMemory, key)
            if mem:
                return mem.value
            return None

    @staticmethod
    async def cleanup_old_events(days_to_keep: int = 30) -> int:
        """Deletes execution events older than the specified number of days."""
        cutoff_date = _now() - timedelta(days=days_to_keep)

        async with get_db_session() as session:
            stmt = delete(ExecutionEvent).where(ExecutionEvent.timestamp < cutoff_date)
            result = await session.execute(stmt)
            await session.commit()

            deleted_count = int(getattr(result, "rowcount", 0))
            if deleted_count > 0:
                logger.info("Cleaned up old execution events", deleted_count=deleted_count, days_kept=days_to_keep)
            return deleted_count
