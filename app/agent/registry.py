from datetime import datetime, timezone
from typing import List
from urllib.parse import urlparse

from sqlalchemy.future import select

from app.core.logger import get_logger
from app.db.models import Strategy as DBStrategy
from app.db.session import get_db_session
from app.schemas.strategy import ActionStrategy

logger = get_logger(__name__)

def _now() -> datetime:
    return datetime.now(timezone.utc)

class StrategyRegistry:
    def __init__(self) -> None:
        pass

    async def get_best_strategies(self, url: str, objective: str, action_type: str) -> List[ActionStrategy]:
        domain = self._extract_domain(url)
        async with get_db_session() as session:
            stmt = select(DBStrategy).where(
                DBStrategy.domain == domain,
                DBStrategy.objective == objective,
                DBStrategy.action == action_type
            ).order_by(DBStrategy.confidence.desc(), DBStrategy.success_count.desc())

            result = await session.execute(stmt)
            db_strategies = result.scalars().all()

            return [
                ActionStrategy(
                    id=str(s.id),
                    domain=s.domain,
                    path_pattern=s.page_pattern,
                    objective=s.objective,
                    action_type=s.action,
                    selector=s.selector,
                    confidence=s.confidence,
                    success_count=s.success_count,
                    failure_count=s.failure_count,
                    last_used=s.updated_at
                ) for s in db_strategies
            ]

    async def record_success(self, strategy_id: str) -> None:
        try:
            db_id = int(strategy_id)
        except ValueError:
            return

        async with get_db_session() as session:
            s = await session.get(DBStrategy, db_id)
            if s:
                s.success_count += 1
                s.updated_at = _now()
                # update confidence
                total = s.success_count + s.failure_count
                s.confidence = s.success_count / total if total > 0 else 1.0
                await session.commit()
                logger.info("Recorded strategy success", strategy_id=strategy_id, confidence=s.confidence)

    async def record_failure(self, strategy_id: str) -> None:
        try:
            db_id = int(strategy_id)
        except ValueError:
            return

        async with get_db_session() as session:
            s = await session.get(DBStrategy, db_id)
            if s:
                s.failure_count += 1
                s.updated_at = _now()
                # update confidence
                total = s.success_count + s.failure_count
                s.confidence = s.success_count / total if total > 0 else 1.0
                await session.commit()
                logger.info("Recorded strategy failure", strategy_id=strategy_id, confidence=s.confidence)

    async def add_strategy(self, url: str, objective: str, action_type: str, selector: str) -> ActionStrategy:
        domain = self._extract_domain(url)
        path = self._extract_path(url)

        async with get_db_session() as session:
            s = DBStrategy(
                domain=domain,
                page_pattern=path,
                objective=objective,
                action=action_type,
                selector=selector,
                strategy_type="ai_discovery"
            )
            session.add(s)
            await session.commit()
            await session.refresh(s)

            strategy = ActionStrategy(
                id=str(s.id),
                domain=s.domain,
                path_pattern=s.page_pattern,
                objective=s.objective,
                action_type=s.action,
                selector=s.selector
            )
            logger.info("Added new strategy", strategy_id=strategy.id, selector=selector)
            return strategy

    def _extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            if parsed.scheme == "file":
                return "local_test_file"
            return parsed.netloc
        except Exception:
            return url

    def _extract_path(self, url: str) -> str:
        try:
            return urlparse(url).path
        except Exception:
            return ""
