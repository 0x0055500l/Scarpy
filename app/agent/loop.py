import time
import uuid
from typing import Any, Optional, Type

from pydantic import BaseModel

from app.agent.ai_layer import AIBrowserLayer
from app.agent.auth import AuthManager
from app.agent.discovery import StrategyDiscovery
from app.agent.history import HistoryManager
from app.agent.planner import AgentPlanner, StepPlan
from app.agent.recovery import RecoveryManager
from app.agent.registry import StrategyRegistry
from app.core.logger import bind_task_context, get_logger
from app.core.metrics import metrics
from app.db.models import Session
from app.db.session import get_db_session
from app.schemas.agent_state import (
    ActionRecord,
    AgentState,
    AgentStatus,
    AuthCredentials,
    ObservationRecord,
    StepPlan,
    VerificationRecord,
)

logger = get_logger(__name__)

class AutonomousWebAgent:
    def __init__(
        self,
        ai_layer: AIBrowserLayer,
        planner: AgentPlanner,
        recovery_manager: RecoveryManager,
        auth_manager: AuthManager,
        registry: StrategyRegistry,
        discovery: StrategyDiscovery,
        max_steps: int = 15,
        max_retries: int = 3,
        global_timeout_sec: int = 300
    ):
        self.ai_layer = ai_layer
        self.planner = planner
        self.recovery_manager = recovery_manager
        self.auth_manager = auth_manager
        self.registry = registry
        self.discovery = discovery

        self.max_steps = max_steps
        self.max_retries = max_retries
        self.global_timeout_sec = global_timeout_sec

        self.state: Optional[AgentState] = None
        self._start_time: float = 0.0

    async def execute(self, goal: str, start_url: str, extract_schema: Optional[Type[BaseModel]] = None, auth_credentials: Optional[AuthCredentials] = None) -> AgentState:
        metrics.start_timer()
        session_id = str(uuid.uuid4())[:8]
        is_new_session = False
        if not self.state:
            is_new_session = True
            self.state = AgentState(
                task_id=self.ai_layer.task_id,
                session_id=session_id,
                goal=goal,
                current_url=start_url
            )
        self.history = HistoryManager(self.state.task_id, self.state.session_id)

        self._start_time = time.time()
        
        # Persist session in DB only once
        if is_new_session:
            async with get_db_session() as session:
                db_session = Session(
                    id=self.state.session_id,
                    task_id=self.state.task_id
                )
                session.add(db_session)
                await session.commit()
            
        agent_logger = bind_task_context(logger, task_id=self.state.task_id, session_id=session_id, url=start_url)
        agent_logger.info("Agent starting execution", goal=goal)

        await self.history.log_event("START_TASK", {"goal": goal, "start_url": start_url})

        try:
            if not self.ai_layer.page:
                await self.ai_layer.start()

            # Planning phase
            if self.state.status == AgentStatus.CREATED:
                self.state.status = AgentStatus.PLANNING
                self.state.plan = await self.planner.create_plan(goal, start_url)
                # Check for auth requirements early if credentials provided
                if auth_credentials:
                    # Inject login step if we have credentials
                    self.state.plan.insert(0, StepPlan(
                        id=str(uuid.uuid4())[:8],
                        action_type="login",
                        description="Authenticate user",
                        target=None,
                        value=None
                    ))
                agent_logger.info(f"Generated {len(self.state.plan)} steps")

            while self.state.current_step_index < len(self.state.plan):
                if time.time() - self._start_time > self.global_timeout_sec:
                    agent_logger.error("Global timeout reached")
                    self.state.status = AgentStatus.FAILED
                    self.state.errors.append("Global timeout reached")
                    break

                if self.state.current_step_index >= self.max_steps:
                    agent_logger.error("Max steps reached")
                    self.state.status = AgentStatus.FAILED
                    self.state.errors.append("Max steps reached")
                    break

                step = self.state.plan[self.state.current_step_index]
                agent_logger.info(f"Executing step {self.state.current_step_index+1}/{len(self.state.plan)}", action=step.action_type, desc=step.description)

                success = await self._execute_step(step, agent_logger, extract_schema, auth_credentials)

                if self.state.status == AgentStatus.WAITING_FOR_USER:
                    agent_logger.info("Agent paused waiting for user input", reason=self.state.paused_reason)
                    break

                if success:
                    # Verification phase
                    self.state.status = AgentStatus.VERIFYING
                    verified = await self._verify_step(step)
                    if verified:
                        self.state.current_step_index += 1
                        self.state.recovery_attempts = 0
                    else:
                        await self._handle_recovery(step, "Verification failed after step execution", agent_logger)
                else:
                    await self._handle_recovery(step, f"Action {step.action_type} failed", agent_logger)

                if self.state.status == AgentStatus.FAILED or self.state.status == AgentStatus.WAITING_FOR_USER:
                    break

            if self.state.status not in [AgentStatus.FAILED, AgentStatus.WAITING_FOR_USER]:
                if self.state.current_step_index >= len(self.state.plan):
                    self.state.status = AgentStatus.COMPLETED
                else:
                    self.state.status = AgentStatus.FAILED
                    self.state.errors.append("Max steps reached without completion")
                    await self.history.log_event("MAX_STEPS_REACHED", {"steps": self.max_steps})

            metrics.record_task_result(success=(self.state.status == AgentStatus.COMPLETED))
            metrics.stop_timer()
            await self.history.log_event("END_TASK", {"final_status": self.state.status.value})
            await self.ai_layer.stop()
            return self.state

        except Exception as e:
            agent_logger.error(f"Agent execution failed: {str(e)}", exc_info=True)
            assert self.state is not None
            self.state.status = AgentStatus.FAILED
            self.state.errors.append(str(e))
            if hasattr(self, 'history'):
                await self.history.log_event("FAILED", {"error": str(e)})
            return self.state
        finally:
            await self.ai_layer.stop()

    async def resume(self, extract_schema: Optional[Type[BaseModel]] = None) -> AgentState:
        """Resumes the agent from a WAITING_FOR_USER state."""
        if not self.state or self.state.status != AgentStatus.WAITING_FOR_USER:
            raise ValueError("Agent is not in a pausable state")

        self.state.status = AgentStatus.ACTING
        self.state.paused_reason = None
        self.state.recovery_attempts = 0

        agent_logger = bind_task_context(logger, task_id=self.state.task_id, session_id=self.state.session_id, url=self.state.current_url)
        agent_logger.info("Agent resuming execution")

        # Assume user has resolved the issue (MFA/Captcha) and we can move to next step
        self.state.current_step_index += 1

        # Resume the main loop logic
        # For simplicity, we just call execute again, it skips init since state exists
        return await self.execute(self.state.goal, self.state.current_url, extract_schema)

    async def _execute_step(self, step: StepPlan, agent_logger: Any, extract_schema: Optional[Type[BaseModel]], auth_credentials: Optional[AuthCredentials] = None) -> bool:
        assert self.state is not None
        start_t = time.time()
        success = False
        error_msg = None

        try:
            if step.action_type == "navigate":
                self.state.status = AgentStatus.NAVIGATING
                target = step.target or self.state.current_url
                await self.ai_layer.navigate(target)
                self.state.current_url = target
                self.state.visited_urls.add(target)
                success = True

            elif step.action_type == "login":
                self.state.status = AgentStatus.ACTING
                if not auth_credentials:
                    error_msg = "No credentials provided for login step"
                else:
                    # Navigate first if needed
                    await self.ai_layer.navigate(self.state.current_url)
                    # Observe elements
                    elements = await self.ai_layer.observe("Find login fields")
                    auth_state = await self.auth_manager.check_auth_state(elements)

                    if auth_state.requires_mfa:
                        self.state.status = AgentStatus.WAITING_FOR_USER
                        self.state.paused_reason = "MFA/CAPTCHA Detected"
                        return False

                    if auth_state.is_authenticated:
                        success = True
                    elif auth_state.requires_login:
                        selectors = await self.auth_manager.identify_login_fields(elements)
                        success = await self.auth_manager.execute_login(self.ai_layer, auth_credentials, selectors)
                        if success:
                            # Re-verify
                            elements = await self.ai_layer.observe("Check if authenticated")
                            auth_state = await self.auth_manager.check_auth_state(elements)
                            if auth_state.requires_mfa:
                                self.state.status = AgentStatus.WAITING_FOR_USER
                                self.state.paused_reason = "MFA/CAPTCHA Detected after login"
                                return False
                            success = auth_state.is_authenticated
                    else:
                        success = True # No login needed

            elif step.action_type == "observe":
                self.state.status = AgentStatus.OBSERVING
                elements = await self.ai_layer.observe(step.description)
                obs = ObservationRecord(step_id=step.id, url=self.state.current_url, elements=elements)
                self.state.observations.append(obs)
                success = True

            elif step.action_type in ["click", "fill"]:
                self.state.status = AgentStatus.ACTING
                success = False

                # 0. Try the planner's explicit target if it's a CSS selector
                if step.target and (step.target.startswith("#") or step.target.startswith(".")):
                    agent_logger.info("Trying planner's explicit target", selector=step.target)
                    if step.action_type == "click":
                        success = await self.ai_layer.click_deterministic(step.target)
                    else:
                        success = await self.ai_layer.fill_deterministic(step.target, step.value or "")

                    if success:
                        new_strat = await self.registry.add_strategy(
                            url=self.state.current_url,
                            objective=step.description,
                            action_type=step.action_type,
                            selector=step.target
                        )
                        await self.registry.record_success(new_strat.id)

                # 1. Try known strategies if planner's target failed or wasn't provided
                if not success:
                    strategies = await self.registry.get_best_strategies(
                        url=self.state.current_url,
                        objective=step.description,
                        action_type=step.action_type
                    )

                    for strategy in strategies:
                        agent_logger.info(f"Trying known strategy (confidence: {strategy.confidence:.2f})", selector=strategy.selector)
                        if step.action_type == "click":
                            success = await self.ai_layer.click_deterministic(strategy.selector)
                        else:
                            success = await self.ai_layer.fill_deterministic(strategy.selector, step.value or "")

                        if success:
                            await self.registry.record_success(strategy.id)
                            break
                        else:
                            await self.registry.record_failure(strategy.id)

                # 2. If no strategies worked, fallback to AI Discovery
                if not success:
                    agent_logger.info("Known strategies failed or none exist. Falling back to AI Discovery.")
                    new_selector = await self.discovery.discover_selector(self.ai_layer, step.description)
                    if new_selector:
                        if step.action_type == "click":
                            success = await self.ai_layer.click_deterministic(new_selector)
                        else:
                            success = await self.ai_layer.fill_deterministic(new_selector, step.value or "")

                        if success:
                            new_strat = await self.registry.add_strategy(
                                url=self.state.current_url,
                                objective=step.description,
                                action_type=step.action_type,
                                selector=new_selector
                            )
                            await self.registry.record_success(new_strat.id)

                # 3. If AI Discovery failed, use Stagehand's generic act
                if not success:
                    agent_logger.info("AI Discovery fallback failed. Using Stagehand AI Act directly.")
                    instruction = step.description
                    if step.value:
                        instruction += f" with value '{step.value}'"
                    success = await self.ai_layer.act(instruction)

            elif step.action_type == "extract":
                if not extract_schema:
                    raise ValueError("extract_schema is required for extraction steps")
                self.state.status = AgentStatus.EXTRACTING
                data = await self.ai_layer.extract(step.description, extract_schema)
                if data:
                    self.state.extracted_data.update(data if isinstance(data, dict) else data.model_dump())
                    success = True
            else:
                success = True # Ignore unknown types

        except Exception as e:
            error_msg = str(e)

        duration = time.time() - start_t
        self.state.actions.append(ActionRecord(
            step_id=step.id, action=step.action_type, target=step.target,
            success=success, duration_ms=duration * 1000, error=error_msg
        ))

        return success

    async def _verify_step(self, step: StepPlan) -> bool:
        assert self.state is not None
        if step.action_type in ["observe", "extract", "login"]:
            return True
            
        # Basic heuristic verification:
        # If we clicked/filled, check if an obvious error message appeared on screen
        if self.ai_layer.page:
            try:
                # Fast check for common error alert roles without LLM overhead
                error_locator = self.ai_layer.page.locator('[role="alert"], .error, .alert-danger, .toast-error')
                if await error_locator.count() > 0 and await error_locator.first.is_visible():
                    error_text = await error_locator.first.inner_text()
                    agent_logger = bind_task_context(logger, task_id=self.state.task_id, session_id=self.state.session_id, url=self.state.current_url)
                    agent_logger.warning("Verification failed: Detected on-screen error", error=error_text)
                    rec = VerificationRecord(step_id=step.id, success=False, reason=f"Detected error: {error_text}")
                    self.state.verifications.append(rec)
                    return False
            except Exception:
                pass

        rec = VerificationRecord(step_id=step.id, success=True, reason="Auto-verified (no alerts)")
        self.state.verifications.append(rec)
        return True

    async def _handle_recovery(self, step: StepPlan, error_msg: str, agent_logger: Any) -> None:
        assert self.state is not None
        self.state.status = AgentStatus.RECOVERING
        self.state.recovery_attempts += 1

        if self.state.recovery_attempts > self.max_retries:
            agent_logger.error("Max recovery attempts reached")
            self.state.status = AgentStatus.FAILED
            self.state.errors.append("Max retries exceeded")
            return

        last_obs = self.state.observations[-1].elements if self.state.observations else []
        strategy = await self.recovery_manager.get_recovery_strategy(step.action_type, error_msg, last_obs)

        if not strategy:
            agent_logger.error("No recovery strategy found")
            self.state.status = AgentStatus.FAILED
            self.state.errors.append("Unrecoverable error")
            return

        agent_logger.info(f"Applying recovery strategy: {strategy.action_type}")
        if strategy.action_type == "ai_act":
            success = await self.ai_layer.act(strategy.instruction)
        elif strategy.action_type == "new_selector":
            success = await self.ai_layer.click_deterministic(strategy.instruction)
        else:
            success = False

        if success:
            agent_logger.info("Recovery successful")
            self.state.current_step_index += 1
            self.state.recovery_attempts = 0
        else:
            agent_logger.warning("Recovery failed")
