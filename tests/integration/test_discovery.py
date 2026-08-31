import asyncio
from typing import Type

import pytest
from pydantic import BaseModel

from app.agent.ai_layer import AIBrowserLayer, OpenAIProvider
from app.agent.discovery_engine import DiscoveryLimits, WebDiscoveryEngine
from app.schemas.discovery import DiscoveryResult

HTML_PAGE_1 = """
<!DOCTYPE html>
<html><body>
    <h1>Product 1</h1>
    <span class="price">$10.00</span>
    <a href="page2.html">Next Page</a>
</body></html>
"""

HTML_PAGE_2 = """
<!DOCTYPE html>
<html><body>
    <h1>Product 2</h1>
    <span class="price">$20.00</span>
    <a href="page3.html">Next Page</a>
    <a href="page1.html">Previous Page</a>
</body></html>
"""

HTML_PAGE_3 = """
<!DOCTYPE html>
<html><body>
    <h1>Product 3</h1>
    <span class="price">$30.00</span>
</body></html>
"""

class MockDiscoveryProvider(OpenAIProvider):
    async def chat(self, prompt: str) -> str:
        # We don't strictly need to mock chat for discovery if extract uses a different path
        # But Stagehand extract does use LLM. We will mock `extract` directly in the test to avoid parsing LLM JSON.
        return '{}'

@pytest.fixture(scope="module")
def page1_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    # Setup 3 interlinked files
    d = tmp_path_factory.mktemp("site")
    p1 = d / "page1.html"
    p2 = d / "page2.html"
    p3 = d / "page3.html"

    p1.write_text(HTML_PAGE_1, encoding="utf-8")
    p2.write_text(HTML_PAGE_2, encoding="utf-8")
    p3.write_text(HTML_PAGE_3, encoding="utf-8")

    return p1.as_uri()

def test_web_discovery_engine(page1_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_test() -> None:
        async def mock_extract(self: "AIBrowserLayer", instruction: str, schema: Type[BaseModel]) -> BaseModel:
            # Simple mock: return data based on current page url
            assert self.page is not None
            url_attr = self.page.url
            if callable(url_attr):
                url_val = url_attr()
                import asyncio
                if asyncio.iscoroutine(url_val):
                    url = await url_val
                else:
                    url = str(url_val)
            else:
                url = str(url_attr)
            print("DEBUG URL IN MOCK_EXTRACT:", url)

            if "page1" in url:
                return schema(name="Product 1", price=10.0) # type: ignore
            elif "page2" in url:
                return schema(name="Product 2", price=20.0) # type: ignore
            elif "page3" in url:
                return schema(name="Product 3", price=30.0) # type: ignore
            return schema(name="Unknown", price=0.0) # type: ignore

        monkeypatch.setattr(AIBrowserLayer, "extract", mock_extract)

        provider = MockDiscoveryProvider()
        layer = AIBrowserLayer(llm_provider=provider)

        limits = DiscoveryLimits(max_pages=2, target_domain="local_test_file")
        engine = WebDiscoveryEngine(ai_layer=layer, limits=limits)

        # The engine creates a DynamicSchema based on the string:
        schema_str = "name: string, price: float"
        objective = "Extract product name and price"

        result = await engine.run(start_url=page1_url, objective=objective, schema_str=schema_str)

        assert isinstance(result, DiscoveryResult)
        assert result.metadata is not None
        # Should have stopped at 2 pages due to max_pages=2
        assert result.metadata.pages_visited_count == 2
        assert len(result.data) == 2
        assert result.data[0]["name"] == "Product 1"
        assert result.data[1]["name"] == "Product 2"

    asyncio.run(run_test())
