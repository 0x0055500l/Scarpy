import asyncio

import pytest
from pydantic import BaseModel

from app.agent.ai_layer import AIBrowserLayer, OpenAIProvider

# Dummy HTML
DUMMY_HTML = """
<!DOCTYPE html>
<html>
<head><title>AI Test</title></head>
<body>
    <h1>Login</h1>
    <input type="text" id="username" placeholder="Enter username">
    <button id="submit-btn">Sign In</button>
    <div id="content">Useful data here</div>
</body>
</html>
"""

class ExtractedData(BaseModel):
    title: str
    content: str

@pytest.fixture(scope="module")
def dummy_page_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    fn = tmp_path_factory.mktemp("data") / "dummy.html"
    fn.write_text(DUMMY_HTML, encoding="utf-8")
    return fn.as_uri()

def test_ai_layer_deterministic(dummy_page_url: str) -> None:
    async def run_test() -> None:
        provider = OpenAIProvider()
        layer = AIBrowserLayer(llm_provider=provider)
        await layer.start()
        await layer.navigate(dummy_page_url)

        # Test deterministic click (Cost control step 1)
        res = await layer.click_deterministic("#submit-btn")
        assert res is True

        # Test failed deterministic click
        res_fail = await layer.click_deterministic("#non-existent")
        assert res_fail is False

        await layer.stop()
    asyncio.run(run_test())

def test_ai_layer_llm_unavailable(dummy_page_url: str) -> None:
    async def run_test() -> None:
        provider = OpenAIProvider()
        layer = AIBrowserLayer(llm_provider=provider)
        await layer.start()
        await layer.navigate(dummy_page_url)

        # Since the API key is fake ("fake-api-key-for-testing"), this should fail gracefully
        res_act = await layer.act("Click the sign in button")
        assert res_act is False

        res_extract = await layer.extract("Extract the main content", ExtractedData)
        assert res_extract is None

        res_observe = await layer.observe("Find the login form")
        # Could be empty list on error
        assert isinstance(res_observe, list)

        await layer.stop()
    asyncio.run(run_test())
