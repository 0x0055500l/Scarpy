import json
import uuid
from typing import List

from app.agent.ai_layer import LLMProvider
from app.core.logger import get_logger
from app.schemas.agent_state import StepPlan

logger = get_logger(__name__)

class AgentPlanner:
    def __init__(self, llm_provider: LLMProvider):
        self.llm_provider = llm_provider

    async def create_plan(self, goal: str, start_url: str) -> List[StepPlan]:
        """Convert a high-level goal into a sequence of actionable steps."""
        logger.info("Creating plan", goal=goal)

        prompt = f"""
You are an autonomous web agent planner. 
Your goal is to break down the user's objective into a step-by-step plan.
Goal: {goal}
Start URL: {start_url}

Create a strict JSON array of steps. Each step must have:
- "action_type": string (e.g. "navigate", "observe", "click", "fill", "extract", "verify")
- "description": string (what to do)
- "target": string (optional, CSS selector or logical target)
- "value": string (optional, what to type if filling)

Keep it deterministic if possible, use AI fallback later.
Respond ONLY with valid JSON. Do not use markdown blocks.
Example:
[
  {{"action_type": "navigate", "description": "Go to start URL", "target": "https://example.com"}},
  {{"action_type": "observe", "description": "Find products list"}}
]
"""
        response_text = await self.llm_provider.chat(prompt)

        try:
            # Clean potential markdown formatting
            if response_text.startswith("```json"):
                response_text = response_text[7:-3]
            elif response_text.startswith("```"):
                response_text = response_text[3:-3]

            steps_data = json.loads(response_text)

            plan = []
            for s in steps_data:
                plan.append(StepPlan(
                    id=str(uuid.uuid4())[:8],
                    action_type=s.get("action_type", "observe"),
                    description=s.get("description", ""),
                    target=s.get("target"),
                    value=s.get("value")
                ))
            return plan
        except Exception as e:
            logger.error("Failed to parse plan from LLM", error=str(e), response=response_text)
            # Fallback trivial plan
            return [
                StepPlan(id=str(uuid.uuid4())[:8], action_type="navigate", description="Go to start URL", target=start_url, value=None),
                StepPlan(id=str(uuid.uuid4())[:8], action_type="observe", description="Observe the page", target=None, value=None),
                StepPlan(id=str(uuid.uuid4())[:8], action_type="extract", description="Extract information based on goal", target=None, value=None)
            ]
