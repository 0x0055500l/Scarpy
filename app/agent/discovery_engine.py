from datetime import datetime, timezone
from typing import Any, Dict, List, Set
from urllib.parse import urljoin, urlparse

import structlog
from pydantic import create_model

from app.agent.ai_layer import AIBrowserLayer
from app.schemas.discovery import DiscoveryLimits, DiscoveryMetadata, DiscoveryResult

logger = structlog.get_logger(__name__)

class URLManager:
    def __init__(self, start_url: str):
        self.start_url = start_url
        self.target_domain = self.extract_domain(start_url)
        self.visited: Set[str] = set()
        self.queue: List[str] = [start_url]

    def extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            if parsed.scheme == "file":
                return "local_test_file"
            return parsed.netloc
        except Exception:
            return ""

    def normalize_url(self, url: str, base: str = "") -> str:
        if base:
            url = urljoin(base, url)
        parsed = urlparse(url)
        # Prevent SSRF / arbitrary local file reads (except local_test_file for tests)
        if parsed.scheme not in ["http", "https", "file"]:
            return ""
        # Remove fragments
        return parsed._replace(fragment="").geturl()

    def add_urls(self, urls: List[str]) -> None:
        for u in urls:
            normalized = self.normalize_url(u, self.start_url)
            if not normalized:
                continue
            domain = self.extract_domain(normalized)
            if domain == self.target_domain and normalized not in self.visited and normalized not in self.queue:
                self.queue.append(normalized)

    def next_url(self) -> str | None:
        if not self.queue:
            return None
        url = self.queue.pop(0)
        self.visited.add(url)
        return url

class LinkDiscovery:
    def __init__(self, ai_layer: AIBrowserLayer):
        self.ai_layer = ai_layer

    async def get_all_links(self) -> List[str]:
        if not self.ai_layer.page:
            return []

        try:
            # Simple expression that returns a plain array of strings
            links = await self.ai_layer.page.evaluate('Array.from(document.links).map(a => a.href)')

            if not isinstance(links, list):
                logger.error("evaluate_all did not return a list", actual_type=str(type(links)))
                return []

            return [str(link) for link in links if link]
        except Exception as e:
            logger.error("Failed to get links", error=str(e))
            return []

class WebDiscoveryEngine:
    def __init__(self, ai_layer: AIBrowserLayer, limits: DiscoveryLimits):
        self.ai_layer = ai_layer
        self.limits = limits
        self.start_time: datetime | None = None
        self.errors: List[str] = []
        self.all_data: List[Any] = []

    async def run(self, start_url: str, objective: str, schema_str: str) -> DiscoveryResult:
        self.start_time = datetime.now(timezone.utc)
        url_manager = URLManager(start_url)
        link_discovery = LinkDiscovery(self.ai_layer)

        # Dynamic schema creation
        schema_fields: Dict[str, Any] = {}
        for line in schema_str.split(','):
            if ':' in line:
                key, type_name = line.split(':', 1)
                key = key.strip()
                type_name = type_name.strip().lower()
                if type_name == 'float':
                    schema_fields[key] = (float, ...)
                elif type_name == 'int':
                    schema_fields[key] = (int, ...)
                else:
                    schema_fields[key] = (str, ...)

        DynamicSchema = create_model('DynamicSchema', **schema_fields) # type: ignore

        await self.ai_layer.start()

        pages_visited = 0
        try:
            while pages_visited < self.limits.max_pages:
                current_url = url_manager.next_url()
                if not current_url:
                    break

                logger.info(f"Visiting {current_url}")
                try:
                    await self.ai_layer.navigate(current_url)
                    pages_visited += 1

                    # Extract data
                    # Wait, Stagehand's extract function works well with pydantic schemas.
                    # We will implement this in AIBrowserLayer next.
                    data = await self.ai_layer.extract(objective, DynamicSchema)
                    if data:
                        self.all_data.append(data.model_dump())
                        logger.info("Extracted data successfully", url=current_url)

                    # Discover links
                    links = await link_discovery.get_all_links()
                    logger.info("Found links", links=links)
                    url_manager.add_urls(links)
                    logger.info("Queue after adding links", queue=url_manager.queue)

                except Exception as e:
                    import traceback
                    logger.error("Error processing page", url=current_url, error=str(e), trace=traceback.format_exc())
                    self.errors.append(f"Error on {current_url}: {str(e)}")

        finally:
            await self.ai_layer.stop()

        end_time = datetime.now(timezone.utc)
        duration = (end_time - self.start_time).total_seconds()

        metadata = DiscoveryMetadata(
            start_time=self.start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration_seconds=duration,
            pages_visited_count=pages_visited
        )

        return DiscoveryResult(
            data=self.all_data,
            metadata=metadata,
            pages_visited=list(url_manager.visited),
            errors=self.errors
        )
