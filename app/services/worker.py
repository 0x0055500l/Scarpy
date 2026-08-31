import asyncio

from app.agent.ai_layer import AIBrowserLayer, OpenAIProvider
from app.agent.auth import AuthManager
from app.agent.discovery import StrategyDiscovery
from app.agent.discovery_engine import WebDiscoveryEngine
from app.agent.loop import AutonomousWebAgent
from app.agent.planner import AgentPlanner
from app.agent.recovery import RecoveryManager
from app.agent.registry import StrategyRegistry
from app.core.config import settings
from app.core.logger import get_logger
from app.db.models import Task
from app.db.session import get_db_session

logger = get_logger(__name__)

class WorkerService:
    """Service to handle background execution of tasks."""

    @staticmethod
    async def process_task(task_id: str) -> None:
        """Process a task in the background."""
        logger.info("Worker starting task", task_id=task_id)

        async with get_db_session() as session:
            task = await session.get(Task, task_id)
            if not task or task.status == "CANCELLED":
                return

            task.status = "RUNNING"
            await session.commit()

            goal = task.goal
            url = task.url
            schema_def = task.schema_definition

        try:
            # Parse options
            options = task.options or {}
            headless = options.get("headless", settings.browser_headless)

            # Initialize agent dependencies
            provider = OpenAIProvider()
            ai_layer = AIBrowserLayer(llm_provider=provider, headless=headless)

            # If the user provided a schema, it's likely a discovery task or extraction task.
            # We will use WebDiscoveryEngine if schema is provided (since Phase 7).
            if schema_def:
                from app.schemas.discovery import DiscoveryLimits
                limits = DiscoveryLimits()
                engine = WebDiscoveryEngine(ai_layer=ai_layer, limits=limits)

                # Convert dict schema back to string if needed, or if run accepts string
                schema_str = ", ".join(f"{k}: {v}" for k, v in schema_def.items())

                result = await engine.run(start_url=url, objective=goal, schema_str=schema_str)

                async with get_db_session() as session:
                    task = await session.get(Task, task_id)
                    if task and task.status != "CANCELLED":
                        task.status = "COMPLETED"
                        task.result = result.model_dump()
                        await session.commit()
            else:
                # Use standard AutonomousWebAgent for generic goals
                planner = AgentPlanner(llm_provider=provider)
                recovery = RecoveryManager(llm_provider=provider)
                auth = AuthManager(llm_provider=provider)
                registry = StrategyRegistry()
                discovery = StrategyDiscovery(llm_provider=provider)

                agent = AutonomousWebAgent(
                    ai_layer=ai_layer,
                    planner=planner,
                    recovery_manager=recovery,
                    auth_manager=auth,
                    registry=registry,
                    discovery=discovery
                )

                agent_state = await agent.execute(goal=goal, start_url=url)

                async with get_db_session() as session:
                    task = await session.get(Task, task_id)
                    if task and task.status != "CANCELLED":
                        task.status = agent_state.status.value
                        task.result = agent_state.extracted_data
                        if agent_state.errors:
                            task.error = "; ".join(agent_state.errors)
                        await session.commit()

        except asyncio.CancelledError:
            logger.info("Worker task cancelled", task_id=task_id)
            async with get_db_session() as session:
                task = await session.get(Task, task_id)
                if task:
                    task.status = "CANCELLED"
                    await session.commit()
            raise

        except Exception as e:
            logger.error("Worker task failed", task_id=task_id, error=str(e), exc_info=True)
            async with get_db_session() as session:
                task = await session.get(Task, task_id)
                if task and task.status != "CANCELLED":
                    task.status = "FAILED"
                    task.error = str(e)
                    await session.commit()

        finally:
            if 'ai_layer' in locals():
                try:
                    await ai_layer.stop()
                except Exception as e:
                    logger.error("Failed to stop ai_layer", error=str(e))

    @classmethod
    def enqueue_task(cls, task_id: str) -> None:
        """Enqueue task execution in asyncio background."""
        # Note: In a production Celery/Arq setup, this would be `worker.delay(task_id)`.
        asyncio.create_task(cls.process_task(task_id))
