import asyncio

import pytest

from app.agent.ai_layer import AIBrowserLayer, OpenAIProvider
from app.agent.loop import AutonomousWebAgent
from app.agent.planner import AgentPlanner
from app.agent.recovery import RecoveryManager
from app.schemas.agent_state import AgentStatus

DUMMY_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
    <h1>Products</h1>
    <div class="product">Product A - $10</div>
    <div class="product">Product B - $20</div>
    <button id="next-page">Next</button>
</body>
</html>
"""

class MockProvider(OpenAIProvider):
    async def chat(self, prompt: str) -> str:
        if "plan" in prompt.lower():
            return '[{"action_type": "navigate", "target": null}, {"action_type": "observe", "description": "view"}, {"action_type": "click", "target": "#next-page"}]'
        elif "recovery" in prompt.lower():
            return '{"action_type": "ai_act", "instruction": "Click next"}'
        return '[]'

@pytest.fixture(scope="module")
def dummy_page_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    fn = tmp_path_factory.mktemp("data") / "dummy.html"
    fn.write_text(DUMMY_HTML, encoding="utf-8")
    return fn.as_uri()

def test_autonomous_agent_success(dummy_page_url: str) -> None:
    async def run_test() -> None:
        provider = MockProvider()
        layer = AIBrowserLayer(llm_provider=provider)
        planner = AgentPlanner(llm_provider=provider)
        recovery = RecoveryManager(llm_provider=provider)
        from app.agent.auth import AuthManager
        from app.agent.discovery import StrategyDiscovery
        from app.agent.registry import StrategyRegistry
        auth = AuthManager(llm_provider=provider)
        registry = StrategyRegistry()
        discovery = StrategyDiscovery(llm_provider=provider)

        agent = AutonomousWebAgent(layer, planner, recovery, auth, registry, discovery, max_steps=5, max_retries=2)
        state = await agent.execute("Test goal", dummy_page_url)

        assert state.status == AgentStatus.COMPLETED
        assert len(state.actions) > 0
        assert len(state.visited_urls) > 0
    asyncio.run(run_test())

def test_autonomous_agent_max_steps(dummy_page_url: str) -> None:
    async def run_test() -> None:
        provider = MockProvider()
        layer = AIBrowserLayer(llm_provider=provider)
        planner = AgentPlanner(llm_provider=provider)
        recovery = RecoveryManager(llm_provider=provider)
        from app.agent.auth import AuthManager
        from app.agent.discovery import StrategyDiscovery
        from app.agent.registry import StrategyRegistry
        auth = AuthManager(llm_provider=provider)
        registry = StrategyRegistry()
        discovery = StrategyDiscovery(llm_provider=provider)

        agent = AutonomousWebAgent(layer, planner, recovery, auth, registry, discovery, max_steps=1)
        state = await agent.execute("Test goal", dummy_page_url)

        assert state.status == AgentStatus.FAILED
        assert "Max steps reached" in state.errors
    asyncio.run(run_test())
