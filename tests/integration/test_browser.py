import asyncio
import os

import pytest

from app.agent.browser import BrowserService
from app.core.exceptions import NavigationError

# Define dummy HTML content
DUMMY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
</head>
<body>
    <h1>Welcome to the Test Page</h1>
    <a href="https://example.com" id="link1">Example Link</a>
    <button id="btn-submit">Submit</button>
    <form>
        <input type="text" name="username" id="username" value="" />
        <input type="hidden" name="csrf" value="secret" />
    </form>
</body>
</html>
"""

@pytest.fixture(scope="module")
def dummy_page_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    fn = tmp_path_factory.mktemp("data") / "dummy.html"
    fn.write_text(DUMMY_HTML, encoding="utf-8")
    return fn.as_uri()

def test_browser_navigate(dummy_page_url: str) -> None:
    async def run_test() -> None:
        service = BrowserService(task_id="test_task", session_id="test_session")
        await service.start()
        await service.new_context()
        result = await service.navigate(dummy_page_url)
        assert result.success is True
        assert result.action == "navigate"
        assert result.evidence is not None
        assert "Final URL" in result.evidence
        await service.stop()
    asyncio.run(run_test())

def test_browser_observe(dummy_page_url: str) -> None:
    async def run_test() -> None:
        service = BrowserService(task_id="test_task", session_id="test_session")
        await service.start()
        await service.new_context()
        await service.navigate(dummy_page_url)
        obs = await service.observe_page()

        assert obs.title == "Test Page"
        assert len(obs.interactive_elements) > 0

        tags = [el.tag for el in obs.interactive_elements]
        assert "button" in tags
        assert "input" in tags
        assert "a" in tags

        hidden_inputs = [el for el in obs.interactive_elements if el.tag == "input" and el.attributes.get("type") == "hidden"]
        assert len(hidden_inputs) == 0
        await service.stop()
    asyncio.run(run_test())

def test_browser_actions(dummy_page_url: str) -> None:
    async def run_test() -> None:
        service = BrowserService(task_id="test_task", session_id="test_session")
        await service.start()
        await service.new_context()
        await service.navigate(dummy_page_url)

        fill_res = await service.fill("#username", "testuser")
        assert fill_res.success is True
        assert fill_res.action == "fill"

        click_res = await service.click("#btn-submit")
        assert click_res.success is True
        assert click_res.action == "click"
        await service.stop()
    asyncio.run(run_test())

def test_browser_action_retry_failure(dummy_page_url: str) -> None:
    async def run_test() -> None:
        service = BrowserService(task_id="test_task", session_id="test_session")
        await service.start()
        await service.new_context()
        await service.navigate(dummy_page_url)

        click_res = await service.click("#non-existent-id")
        assert click_res.success is False
        assert click_res.error_message is not None
        assert "Failed to click" in click_res.error_message
        assert click_res.screenshot_path is not None
        assert os.path.exists(click_res.screenshot_path)
        await service.stop()
    asyncio.run(run_test())

def test_browser_navigation_error() -> None:
    async def run_test() -> None:
        service = BrowserService(task_id="test_task", session_id="test_session")
        await service.start()
        await service.new_context()
        with pytest.raises(NavigationError):
            await service.navigate("http://this-does-not-exist.local.test.invalid")
        await service.stop()
    asyncio.run(run_test())
