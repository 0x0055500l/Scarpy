import asyncio
import os
import uuid
from typing import Any, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from app.core.config import settings
from app.core.exceptions import ActionError, BrowserError, NavigationError
from app.core.logger import bind_task_context, get_logger
from app.schemas.browser import ActionResult, ElementObservation, PageObservation

logger = get_logger(__name__)


class BrowserService:
    """Independent Browser Engine using Playwright."""

    def __init__(
        self,
        task_id: str = "default_task",
        session_id: Optional[str] = None,
        screenshots_dir: str = "screenshots",
    ):
        self.task_id = task_id
        self.session_id = session_id or str(uuid.uuid4())
        self.screenshots_dir = screenshots_dir
        self.logger = bind_task_context(
            logger, task_id=self.task_id, session_id=self.session_id, url=""
        )

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        os.makedirs(self.screenshots_dir, exist_ok=True)

    async def start(self) -> None:
        """Start the Playwright engine and launch the browser."""
        self.logger.debug("Starting browser service")
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=settings.browser_headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self.logger.info("Browser service started successfully")
        except Exception as e:
            self.logger.error("Failed to start browser service", error=str(e))
            raise BrowserError(f"Could not start browser: {e}") from e

    async def new_context(self) -> None:
        """Create a new isolated browser context and page."""
        if not self._browser:
            raise BrowserError("Browser is not started. Call start() first.")

        try:
            context_args: dict[str, Any] = {
                "viewport": {"width": 1280, "height": 800},
            }
            if settings.browser_user_agent:
                context_args["user_agent"] = settings.browser_user_agent

            self._context = await self._browser.new_context(**context_args)
            if settings.browser_tracing:
                await self._context.tracing.start(screenshots=True, snapshots=True, sources=True)

            self._page = await self._context.new_page()
            self.logger.debug("New browser context and page created")
        except Exception as e:
            self.logger.error("Failed to create new context", error=str(e))
            raise BrowserError(f"Could not create context: {e}") from e

    async def close_context(self) -> None:
        """Close the current context and save tracing if enabled."""
        if self._context:
            if settings.browser_tracing:
                trace_path = os.path.join(self.screenshots_dir, f"trace_{self.session_id}.zip")
                await self._context.tracing.stop(path=trace_path)

            await self._context.close()
            self._context = None
            self._page = None
            self.logger.debug("Browser context closed")

    async def stop(self) -> None:
        """Stop the browser and Playwright engine entirely."""
        await self.close_context()
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self.logger.info("Browser service stopped")

    async def _capture_screenshot(self, name_prefix: str) -> str:
        """Capture a screenshot and save it."""
        if not self._page:
            return ""

        file_name = f"{name_prefix}_{self.task_id}_{self.session_id}_{uuid.uuid4().hex[:8]}.png"
        path = os.path.join(self.screenshots_dir, file_name)
        try:
            await self._page.screenshot(path=path, full_page=True)
            self.logger.info("Screenshot captured", path=path)
            return path
        except Exception as e:
            self.logger.error("Failed to capture screenshot", error=str(e))
            return ""

    async def navigate(self, url: str) -> ActionResult:
        """Navigate to a URL robustly."""
        if not self._page:
            raise BrowserError("No page available. Call new_context() first.")

        self.logger = self.logger.bind(url=url, action="navigate")
        self.logger.info(f"Navigating to {url}")

        try:
            response = await self._page.goto(
                url,
                timeout=settings.browser_timeout,
                wait_until="domcontentloaded"
            )

            if response and not response.ok:
                error_msg = f"HTTP Error: {response.status} {response.status_text}"
                screenshot = await self._capture_screenshot("nav_error")
                return ActionResult(
                    success=False,
                    action="navigate",
                    target=url,
                    error_message=error_msg,
                    screenshot_path=screenshot
                )

            # Wait for network idle to ensure dynamic content loads (robust navigation)
            try:
                await self._page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                self.logger.warning("Network idle timeout reached, proceeding anyway")

            current_url = self._page.url
            return ActionResult(
                success=True,
                action="navigate",
                target=url,
                evidence=f"Final URL: {current_url}"
            )

        except PlaywrightTimeoutError as e:
            self.logger.error("Navigation timeout", error=str(e))
            screenshot = await self._capture_screenshot("timeout")
            raise NavigationError(f"Timeout navigating to {url}") from e
        except Exception as e:
            self.logger.error("Navigation failed", error=str(e))
            screenshot = await self._capture_screenshot("nav_fail")
            raise NavigationError(f"Failed to navigate: {e}") from e

    async def observe_page(self) -> PageObservation:
        """Observe the current page, selectively capturing interactive elements."""
        if not self._page:
            raise BrowserError("No page available.")

        url = self._page.url
        title = await self._page.title()

        # JS to extract selective interactive elements without grabbing the whole DOM
        js_code = """
        () => {
            const elements = Array.from(document.querySelectorAll('a, button, input, select, textarea, form'));
            return elements.map(el => {
                const attrs = {};
                for (let i = 0; i < el.attributes.length; i++) {
                    attrs[el.attributes[i].name] = el.attributes[i].value;
                }
                let text = el.innerText || el.value || '';
                return {
                    tag: el.tagName.toLowerCase(),
                    text: text.trim().substring(0, 100), // Limit text length
                    attributes: attrs
                };
            }).filter(item => {
                // Filter out hidden or useless elements
                if (item.tag === 'input' && item.attributes.type === 'hidden') return false;
                return true;
            }).slice(0, 100); // Limit total elements to prevent massive payloads
        }
        """
        try:
            raw_elements = await self._page.evaluate(js_code)
            interactive_elements = [
                ElementObservation(tag=el["tag"], text=el["text"], attributes=el["attributes"])
                for el in raw_elements
            ]
        except Exception as e:
            self.logger.warning("Failed to observe elements via JS", error=str(e))
            interactive_elements = []

        return PageObservation(url=url, title=title, interactive_elements=interactive_elements)

    async def click(self, selector: str) -> ActionResult:
        """Click an element, with retry logic."""
        return await self._execute_action("click", selector)

    async def fill(self, selector: str, text: str) -> ActionResult:
        """Fill an input field."""
        return await self._execute_action("fill", selector, text)

    async def _execute_action(self, action_name: str, selector: str, text: Optional[str] = None) -> ActionResult:
        """Execute a browser action with retries."""
        if not self._page:
            raise BrowserError("No page available.")

        self.logger = self.logger.bind(action=action_name)

        for attempt in range(1, settings.max_retries + 1):
            try:
                self.logger.debug(f"Attempt {attempt} for {action_name} on {selector}")

                # Wait for element to be visible
                locator = self._page.locator(selector).first
                await locator.wait_for(state="visible", timeout=10000)

                if action_name == "click":
                    await locator.click(timeout=5000)
                elif action_name == "fill" and text is not None:
                    await locator.fill(text, timeout=5000)
                else:
                    raise ActionError(f"Unsupported action: {action_name}")

                return ActionResult(
                    success=True,
                    action=action_name,
                    target=selector,
                    evidence=f"{action_name} executed successfully"
                )

            except PlaywrightTimeoutError:
                self.logger.warning(f"Timeout on {action_name} for {selector}, attempt {attempt}")
            except Exception as e:
                self.logger.warning(f"Error on {action_name} for {selector}, attempt {attempt}", error=str(e))

            if attempt < settings.max_retries:
                await asyncio.sleep(1) # Small deterministic backoff between retries

        # If we exit the loop, all retries failed
        error_msg = f"Failed to {action_name} on {selector} after {settings.max_retries} attempts"
        self.logger.error(error_msg)
        screenshot = await self._capture_screenshot(f"action_error_{action_name}")

        return ActionResult(
            success=False,
            action=action_name,
            target=selector,
            error_message=error_msg,
            screenshot_path=screenshot
        )
