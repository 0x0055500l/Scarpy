import asyncio

import pytest

from app.agent.ai_layer import AIBrowserLayer, OpenAIProvider
from app.agent.auth import AuthManager
from app.agent.discovery import StrategyDiscovery
from app.agent.loop import AutonomousWebAgent
from app.agent.planner import AgentPlanner
from app.agent.recovery import RecoveryManager
from app.agent.registry import StrategyRegistry
from app.schemas.agent_state import AgentStatus

HTML_VERSION_A = """
<!DOCTYPE html>
<html><body>
    <button id="submit-btn" onclick="document.body.innerHTML='<h1>Success A</h1>'">Submit</button>
</body></html>
"""

HTML_VERSION_B = """
<!DOCTYPE html>
<html><body>
    <button class="action-submit" onclick="document.body.innerHTML='<h1>Success B</h1>'">Submit</button>
</body></html>
"""

HTML_VERSION_C = """
<!DOCTYPE html>
<html><body>
    <div role="button" aria-label="Confirm" onclick="document.body.innerHTML='<h1>Success C</h1>'">Confirm</div>
</body></html>
"""

class MockSelfHealingProvider(OpenAIProvider):
    async def chat(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if "plan" in prompt_lower:
            return '[{"action_type": "navigate", "description": "go to start page"}, {"action_type": "click", "description": "Click the submit button"}]'
        elif "determine the single most robust css selector" in prompt_lower:
            if "class=\"action-submit\"" in prompt_lower:
                return '{"selector": ".action-submit"}'
            elif "role=\"button\"" in prompt_lower:
                return '{"selector": "[aria-label=\\"Confirm\\"]"}'
            else:
                return '{"selector": "#submit-btn"}'
        return '{}'

@pytest.fixture(scope="module")
def page_a_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    fn = tmp_path_factory.mktemp("data") / "a.html"
    fn.write_text(HTML_VERSION_A, encoding="utf-8")
    return fn.as_uri()

@pytest.fixture(scope="module")
def page_b_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    fn = tmp_path_factory.mktemp("data") / "b.html"
    fn.write_text(HTML_VERSION_B, encoding="utf-8")
    return fn.as_uri()

@pytest.fixture(scope="module")
def page_c_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    fn = tmp_path_factory.mktemp("data") / "c.html"
    fn.write_text(HTML_VERSION_C, encoding="utf-8")
    return fn.as_uri()

def test_self_healing_workflow(page_a_url: str, page_b_url: str, page_c_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_test() -> None:
        obs_count = 0
        async def mock_observe(self: "AIBrowserLayer", instruction: str = "") -> list:
            # We don't need to check URL, we can just use a call counter
            nonlocal obs_count
            obs_count += 1
            if obs_count == 1: # a.html
                return ['<button id="submit-btn">Submit</button>']
            elif obs_count == 2: # b.html
                return ['<button class="action-submit">Submit</button>']
            else: # c.html
                return ['<div role="button" aria-label="Confirm">Confirm</div>']
        monkeypatch.setattr(AIBrowserLayer, "observe", mock_observe)

        provider = MockSelfHealingProvider()
        layer = AIBrowserLayer(llm_provider=provider)
        planner = AgentPlanner(llm_provider=provider)
        recovery = RecoveryManager(llm_provider=provider)
        auth = AuthManager(llm_provider=provider)
        registry = StrategyRegistry()
        discovery = StrategyDiscovery(llm_provider=provider)

        agent = AutonomousWebAgent(layer, planner, recovery, auth, registry, discovery, max_steps=5, max_retries=1)

        # --- VERSION A ---
        # The agent should use AI Discovery on first run since registry is empty
        state_a = await agent.execute("Click submit", page_a_url)
        assert state_a.status == AgentStatus.COMPLETED
        # Registry should have 1 strategy, 1 success
        strategies_a = await registry.get_best_strategies(page_a_url, "Click the submit button", "click")
        assert len(strategies_a) == 1
        assert strategies_a[0].selector == "#submit-btn"
        assert strategies_a[0].success_count == 1

        # Reset state for next run, but KEEP registry
        agent.state = None

        # --- VERSION B ---
        # The agent should try #submit-btn, fail, use AI Discovery, find .action-submit, succeed
        state_b = await agent.execute("Click submit", page_b_url)
        assert state_b.status == AgentStatus.COMPLETED

        # The original strategy should have a failure recorded (can check by getting it)
        strategies_b_fail = await registry.get_best_strategies(page_a_url, "Click the submit button", "click")
        # Now there are 2 strategies for this domain
        assert len(strategies_b_fail) == 2

        strat_a = next(s for s in strategies_b_fail if s.selector == "#submit-btn")
        assert strat_a.failure_count == 1

        # The new strategy should be recorded and successful
        strat_b = next(s for s in strategies_b_fail if s.selector == ".action-submit")
        assert strat_b.success_count == 1

        # --- VERSION C ---
        # Try both known strategies, fail, AI Discovery finds [aria-label="Confirm"]
        agent.state = None
        state_c = await agent.execute("Click submit", page_c_url)
        assert state_c.status == AgentStatus.COMPLETED

        strategies_c = await registry.get_best_strategies(page_c_url, "Click the submit button", "click")
        assert len(strategies_c) == 3

        strat_c = next(s for s in strategies_c if s.selector == '[aria-label="Confirm"]')
        assert strat_c.success_count == 1

    asyncio.run(run_test())
