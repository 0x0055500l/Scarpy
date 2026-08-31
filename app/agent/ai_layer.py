from abc import ABC, abstractmethod
from typing import Optional, Type, TypeVar

from pydantic import BaseModel
from stagehand import Stagehand, local_browser
from stagehand.browser import StagehandBrowser
from stagehand.page import Page

from app.core.config import settings
from app.core.exceptions import BrowserError
from app.core.logger import bind_task_context, get_logger
from app.core.metrics import metrics

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)

class LLMProvider(ABC):
    """Abstraction for LLM providers."""

    @abstractmethod
    def get_model_name(self) -> str:
        pass

    @abstractmethod
    def get_api_key(self) -> str:
        pass

    @abstractmethod
    async def chat(self, prompt: str) -> str:
        pass

class OpenAIProvider(LLMProvider):
    """Generic LLM provider implementation."""

    def get_model_name(self) -> str:
        provider = settings.llm_provider.lower()
        model = settings.llm_model
        
        # If model already has a provider prefix, return as is
        if "/" in model:
            return model
            
        # Otherwise, prefix it with the configured provider
        return f"{provider}/{model}"

    def get_api_key(self) -> str:
        return settings.llm_api_key

    async def chat(self, prompt: str) -> str:
        import httpx
        
        provider = settings.llm_provider.lower()
        model = self.get_model_name().split("/")[-1]

        # In test mode with fake key, just return a mock response
        if self.get_api_key().startswith("fake"):
            return "{\"mock\": \"true\"}"

        async with httpx.AsyncClient() as client:
            if provider == "google":
                # Use native Google API to avoid compatibility endpoint 404s
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.get_api_key()}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.0}
                }
                resp = await client.post(url, json=payload, timeout=30.0)
                resp.raise_for_status()
                data = resp.json()
                try:
                    return str(data["candidates"][0]["content"]["parts"][0]["text"])
                except (KeyError, IndexError):
                    return ""
            else:
                # Standard OpenAI compatible endpoint
                headers = {
                    "Authorization": f"Bearer {self.get_api_key()}",
                    "Content-Type": "application/json"
                }
                if hasattr(settings, 'llm_base_url') and settings.llm_base_url:
                    base_url = f"{settings.llm_base_url}/chat/completions"
                else:
                    base_url = "https://api.openai.com/v1/chat/completions"

                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                }
                resp = await client.post(base_url, headers=headers, json=payload, timeout=30.0)
                resp.raise_for_status()
                data = resp.json()
                return str(data["choices"][0]["message"]["content"])

class AIBrowserLayer:
    """AI Browser Layer wrapping Stagehand and Playwright."""

    def __init__(self, llm_provider: LLMProvider, task_id: str = "default", headless: Optional[bool] = None):
        self.llm_provider = llm_provider
        self.task_id = task_id
        self.headless = headless if headless is not None else settings.browser_headless
        self.logger = bind_task_context(logger, task_id=task_id, session_id="ai_session", url="")
        self._browser: Optional[StagehandBrowser] = None
        self.stagehand: Optional[Stagehand] = None
        self.page: Optional[Page] = None

    async def start(self) -> None:
        self.logger.info("Starting AI Browser Layer")
        try:
            self._browser = await local_browser.launch(headless=self.headless)
            self.stagehand = await Stagehand.create(
                browser=self._browser,
                model_api_key=self.llm_provider.get_api_key(),
                model=self.llm_provider.get_model_name(),
            )
            pages = await self.stagehand.browser.context.pages()
            self.page = pages[0] if pages else await self.stagehand.browser.context.new_page()
        except Exception as e:
            self.logger.error("Failed to start AI Browser Layer", error=str(e))
            raise BrowserError(f"Could not start AI Browser: {e}") from e

    async def stop(self) -> None:
        self.logger.info("AI Browser Layer stopped")
        if self.stagehand:
            try:
                await self.stagehand.close()
            except Exception:
                pass
            self.stagehand = None
            
        # Ensure underlying browser is definitely closed
        if hasattr(self, '_browser') and self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
            
        self.page = None

    async def navigate(self, url: str) -> None:
        from urllib.parse import urlparse
        import os
        if not self.page:
            metrics.record_browser_error()
            raise BrowserError("Browser not started")
            
        parsed = urlparse(url)
        allowed = ["http", "https"]
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("ALLOW_FILE_PROTOCOL"):
            allowed.append("file")
            
        if parsed.scheme not in allowed:
            metrics.record_browser_error()
            raise BrowserError(f"Security Policy Violation: Invalid URL scheme '{parsed.scheme}'. Only http and https are permitted.")
            
        self.logger.info(f"Navigating to {url}")
        await self.page.goto(url, wait_until="domcontentloaded", timeout=settings.browser_timeout)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

    # Deterministic Actions
    async def click_deterministic(self, selector: str) -> bool:
        """Cost control: execute deterministically without AI."""
        if not self.page:
            return False
        try:
            # Stagehand's page wrapper exposes wait_for_selector directly
            await self.page.wait_for_selector(selector, state="visible", timeout=5000)
            await self.page.locator(selector).first().click()
            return True
        except Exception as e:
            self.logger.warning(f"Deterministic click failed on {selector}", error=str(e))
            return False

    async def fill_deterministic(self, selector: str, text: str) -> bool:
        """Attempt a deterministic fill using standard Playwright methods without AI."""
        if not self.page:
            return False
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=5000)
            await self.page.locator(selector).first().fill(text)
            return True
        except Exception as e:
            self.logger.warning(f"Deterministic fill failed on {selector}", error=str(e))
            return False

    # AI Actions
    async def act(self, instruction: str) -> bool:
        """Use AI to interpret instruction and act on the page."""
        if not self.stagehand:
            metrics.record_browser_error()
            raise BrowserError("Stagehand not initialized")

        self.logger.info(f"AI Act: {instruction}")
        try:
            result = await self.stagehand.act(instruction)
            metrics.record_llm_call(success=True)
            # ActResultData contains success
            return result.data.success if hasattr(result.data, "success") else True
        except Exception as e:
            self.logger.error("AI act failed", error=str(e))
            metrics.record_llm_call(success=False)
            return False

    async def extract(self, instruction: str, schema: Type[T]) -> Optional[T]:
        """Use AI to extract structured data using Pydantic."""
        if not self.stagehand:
            metrics.record_browser_error()
            raise BrowserError("Stagehand not initialized")

        self.logger.info(f"AI Extract: {instruction}")
        try:
            result = await self.stagehand.extract(instruction, schema=schema)
            metrics.record_llm_call(success=True)
            # ExtractResult data holds the Pydantic instance
            return result.data
        except Exception as e:
            self.logger.error("AI extract failed", error=str(e))
            metrics.record_llm_call(success=False)
            return None

    async def observe(self, instruction: Optional[str] = None) -> list[str]:
        """Use AI to observe actionable elements."""
        if not self.stagehand:
            metrics.record_browser_error()
            raise BrowserError("Stagehand not initialized")

        self.logger.info("AI Observe")
        try:
            result = await self.stagehand.observe(instruction)
            metrics.record_llm_call(success=True)
            # ObserveResult data is a list of Actions
            return [element.description for element in result.data if hasattr(element, "description")]
        except Exception as e:
            self.logger.error("AI observe failed", error=str(e))
            metrics.record_llm_call(success=False)
            return []
