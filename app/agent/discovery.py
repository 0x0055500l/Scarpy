import json
from typing import Optional

from app.agent.ai_layer import AIBrowserLayer, LLMProvider
from app.core.logger import get_logger

logger = get_logger(__name__)

class StrategyDiscovery:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    async def discover_selector(self, ai_layer: AIBrowserLayer, objective: str) -> Optional[str]:
        """Observes the page and asks the LLM to discover the best CSS selector for the objective."""
        try:
            elements = await ai_layer.observe(f"Find: {objective}")
            if not elements:
                logger.warning("No elements found during discovery observation")
                return None

            prompt = f"""
You are an expert Web Automation engineer.
Your objective is: "{objective}"

Here are the interactive elements on the page that might match this objective:
{chr(10).join(elements[:50])}

Determine the single most robust CSS selector that uniquely identifies the target element for this objective.
Prefer IDs, data attributes (e.g. data-testid), and unique semantic combinations.
Return ONLY valid JSON with a single key "selector".
Example:
{{"selector": "#submit-btn"}}
"""
            response = await self.llm_provider.chat(prompt)

            if response.startswith("```json"):
                response = response[7:-3]
            elif response.startswith("```"):
                response = response[3:-3]

            data = json.loads(response.strip())
            selector = data.get("selector")

            if selector:
                logger.info("AI discovered new selector", selector=selector)
                return str(selector)

            return None
        except Exception as e:
            logger.error("Failed during AI strategy discovery", error=str(e))
            return None
