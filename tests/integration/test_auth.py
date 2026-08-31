import asyncio

import pytest
from pydantic import SecretStr

from app.agent.ai_layer import AIBrowserLayer, OpenAIProvider
from app.agent.auth import AuthManager
from app.agent.loop import AutonomousWebAgent
from app.agent.planner import AgentPlanner
from app.agent.recovery import RecoveryManager
from app.schemas.agent_state import AgentStatus, AuthCredentials

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>Login</title></head>
<body>
    <h1>Login required</h1>
    <input type="text" id="username" placeholder="Username">
    <input type="password" id="password" placeholder="Password">
    <button id="login-btn" onclick="document.body.innerHTML='<h1>Dashboard</h1>';">Login</button>
</body>
</html>
"""

MFA_HTML = """
<!DOCTYPE html>
<html>
<head><title>Login</title></head>
<body>
    <h1>Login required</h1>
    <input type="text" id="username" placeholder="Username">
    <input type="password" id="password" placeholder="Password">
    <button id="login-btn" onclick="document.body.innerHTML='<h1>MFA Required</h1><input type=\"text\" placeholder=\"Enter code\">';">Login</button>
</body>
</html>
"""

class MockAuthProvider(OpenAIProvider):
    def __init__(self, is_mfa: bool = False):
        self.is_mfa = is_mfa
        self.call_count = 0

    async def chat(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if "analyze these page elements" in prompt_lower:
            if "<h1>dashboard</h1>" in prompt_lower:
                return '{"requires_login": false, "requires_mfa": false, "is_authenticated": true}'
            elif "<h1>mfa required</h1>" in prompt_lower:
                return '{"requires_login": false, "requires_mfa": true, "is_authenticated": false}'
            else:
                return '{"requires_login": true, "requires_mfa": false, "is_authenticated": false}'
        elif "css selectors for the login form" in prompt_lower:
            return '{"username_selector": "#username", "password_selector": "#password", "submit_selector": "#login-btn"}'
        elif "plan" in prompt_lower:
            return '[]'
        elif "recovery" in prompt_lower:
            return '{"action_type": "abort", "instruction": ""}'
        return '{}'

import pathlib


@pytest.fixture
def login_page_url(tmp_path: pathlib.Path) -> str:
    fn = tmp_path / "login.html"
    fn.write_text(LOGIN_HTML, encoding="utf-8")
    return fn.as_uri()

@pytest.fixture
def mfa_page_url(tmp_path: pathlib.Path) -> str:
    fn = tmp_path / "mfa.html"
    fn.write_text(MFA_HTML, encoding="utf-8")
    return fn.as_uri()

def test_auth_success(login_page_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_test() -> None:
        call_count = {"observe": 0}
        async def mock_observe(self: "AIBrowserLayer", instruction: str = "") -> list:
            call_count["observe"] += 1
            print(f"DEBUG MOCK OBSERVE SUCCESS CALL {call_count['observe']}")
            if call_count["observe"] == 1:
                return ["<input id='username'>", "<input id='password'>", "<button id='login-btn'>"]
            return ["<h1>Dashboard</h1>"]
        monkeypatch.setattr(AIBrowserLayer, "observe", mock_observe)

        provider = MockAuthProvider()
        layer = AIBrowserLayer(llm_provider=provider)
        planner = AgentPlanner(llm_provider=provider)
        recovery = RecoveryManager(llm_provider=provider)
        auth = AuthManager(llm_provider=provider)
        from app.agent.discovery import StrategyDiscovery
        from app.agent.registry import StrategyRegistry
        registry = StrategyRegistry()
        discovery = StrategyDiscovery(llm_provider=provider)

        agent = AutonomousWebAgent(layer, planner, recovery, auth, registry, discovery, max_steps=5, max_retries=1)
        creds = AuthCredentials(username="test_user", password=SecretStr("super_secret_123"))
        state = await agent.execute("Do something", login_page_url, auth_credentials=creds)

        assert state.status == AgentStatus.COMPLETED
        state_str = state.model_dump_json()
        assert "super_secret_123" not in state_str
    asyncio.run(run_test())

def test_auth_mfa_triggers_waiting(mfa_page_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_test() -> None:
        call_count = {"observe": 0}
        async def mock_observe(self: "AIBrowserLayer", instruction: str = "") -> list:
            call_count["observe"] += 1
            print(f"DEBUG MOCK OBSERVE MFA CALL {call_count['observe']}")
            if call_count["observe"] == 1:
                return ["<input id='username'>", "<input id='password'>", "<button id='login-btn'>"]
            return ["<h1>MFA Required</h1>"]
        monkeypatch.setattr(AIBrowserLayer, "observe", mock_observe)

        provider = MockAuthProvider(is_mfa=True)
        layer = AIBrowserLayer(llm_provider=provider)
        planner = AgentPlanner(llm_provider=provider)
        recovery = RecoveryManager(llm_provider=provider)
        auth = AuthManager(llm_provider=provider)
        from app.agent.discovery import StrategyDiscovery
        from app.agent.registry import StrategyRegistry
        registry = StrategyRegistry()
        discovery = StrategyDiscovery(llm_provider=provider)

        agent = AutonomousWebAgent(layer, planner, recovery, auth, registry, discovery, max_steps=5, max_retries=1)
        creds = AuthCredentials(username="test_user", password=SecretStr("super_secret_123"))
        state = await agent.execute("Do something", mfa_page_url, auth_credentials=creds)

        assert state.status == AgentStatus.WAITING_FOR_USER
        assert state.paused_reason == "MFA/CAPTCHA Detected after login"

        # Resume manually
        state = await agent.resume()
        assert state.status == AgentStatus.COMPLETED

    asyncio.run(run_test())
