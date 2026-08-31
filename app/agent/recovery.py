import json
from typing import List, Optional

from app.agent.ai_layer import LLMProvider
from app.core.logger import get_logger

logger = get_logger(__name__)

class RecoveryStrategy:
    def __init__(self, action_type: str, instruction: str):
        self.action_type = action_type  # e.g., 'ai_act', 'new_selector', 'manual'
        self.instruction = instruction

class RecoveryManager:
    def __init__(self, llm_provider: LLMProvider):
        self.llm_provider = llm_provider

    async def get_recovery_strategy(self, failed_action: str, error_msg: str, observation: List[str]) -> Optional[RecoveryStrategy]:
        logger.info("Generating recovery strategy", failed_action=failed_action, error=error_msg)

        prompt = f"""
The web agent failed to execute an action.
Failed Action: {failed_action}
Error: {error_msg}

Current Page Observations (available interactive elements):
{chr(10).join(observation[:20])}

Suggest a recovery strategy.
Return JSON ONLY with:
- "action_type": "ai_act" or "new_selector"
- "instruction": The natural language instruction for AI, or the new CSS selector.

If you cannot recover, return {{"action_type": "abort", "instruction": ""}}
"""
        response_text = await self.llm_provider.chat(prompt)
        try:
            if response_text.startswith("```json"):
                response_text = response_text[7:-3]
            elif response_text.startswith("```"):
                response_text = response_text[3:-3]

            data = json.loads(response_text)
            action_type = data.get("action_type", "abort")
            if action_type == "abort":
                return None
            return RecoveryStrategy(action_type=action_type, instruction=data.get("instruction", ""))
        except Exception as e:
            logger.error("Failed to parse recovery strategy", error=str(e), response=response_text)
            return RecoveryStrategy(action_type="ai_act", instruction=f"Attempt to {failed_action} using natural language")
