import json
from typing import List, Optional

from pydantic import BaseModel

from app.agent.ai_layer import AIBrowserLayer, LLMProvider
from app.core.logger import get_logger
from app.schemas.agent_state import AuthCredentials

logger = get_logger(__name__)

class LoginSelectors(BaseModel):
    username_selector: Optional[str]
    password_selector: Optional[str]
    submit_selector: Optional[str]

class AuthCheckResult(BaseModel):
    requires_login: bool
    requires_mfa: bool
    is_authenticated: bool

class AuthManager:
    def __init__(self, llm_provider: LLMProvider):
        self.llm_provider = llm_provider

    async def check_auth_state(self, observation: List[str]) -> AuthCheckResult:
        """Determines the current authentication state from the page elements."""
        prompt = f"""
Analyze these page elements and determine the authentication state:
{chr(10).join(observation[:30])}

Return ONLY valid JSON with boolean values:
- "requires_login": true if there is a login form (username/email, password fields).
- "requires_mfa": true if the page is asking for an MFA code, 2FA, OTP, or showing a CAPTCHA.
- "is_authenticated": true if there are indicators of being logged in (like "Logout", "My Profile", "Dashboard").
"""
        response = await self.llm_provider.chat(prompt)
        try:
            if response.startswith("```json"):
                response = response[7:-3]
            elif response.startswith("```"):
                response = response[3:-3]
            data = json.loads(response)
            return AuthCheckResult(
                requires_login=bool(data.get("requires_login")),
                requires_mfa=bool(data.get("requires_mfa")),
                is_authenticated=bool(data.get("is_authenticated"))
            )
        except Exception as e:
            logger.error("Failed to parse auth state", error=str(e))
            return AuthCheckResult(requires_login=False, requires_mfa=False, is_authenticated=False)

    async def identify_login_fields(self, observation: List[str]) -> LoginSelectors:
        """Finds CSS selectors for login fields without sending passwords to the LLM."""
        prompt = f"""
Find the CSS selectors for the login form based on these elements:
{chr(10).join(observation[:30])}

Focus on id, name, placeholder, role, label, or type attributes.
Return ONLY valid JSON:
- "username_selector": CSS selector for username/email.
- "password_selector": CSS selector for password.
- "submit_selector": CSS selector for the submit/login button.
"""
        response = await self.llm_provider.chat(prompt)
        try:
            if response.startswith("```json"):
                response = response[7:-3]
            elif response.startswith("```"):
                response = response[3:-3]
            data = json.loads(response)
            return LoginSelectors(
                username_selector=data.get("username_selector"),
                password_selector=data.get("password_selector"),
                submit_selector=data.get("submit_selector")
            )
        except Exception as e:
            logger.error("Failed to parse login selectors", error=str(e))
            return LoginSelectors(username_selector=None, password_selector=None, submit_selector=None)

    async def execute_login(self, ai_layer: AIBrowserLayer, credentials: AuthCredentials, selectors: LoginSelectors) -> bool:
        """Executes the login securely using deterministic methods to avoid leaking passwords."""
        logger.info("Executing secure login")
        if not selectors.username_selector or not selectors.password_selector or not selectors.submit_selector:
            logger.warning("Missing selectors for login")
            return False

        # Use deterministic fill to keep password out of LLM prompts and logs
        u_success = await ai_layer.fill_deterministic(selectors.username_selector, credentials.username)
        p_success = await ai_layer.fill_deterministic(selectors.password_selector, credentials.password.get_secret_value())

        if not u_success or not p_success:
            logger.warning("Failed to deterministically fill credentials")
            return False

        s_success = await ai_layer.click_deterministic(selectors.submit_selector)
        if not s_success:
            logger.warning("Failed to deterministically click submit")
            return False

        # Give page time to load or show errors
        if ai_layer.page:
            try:
                await ai_layer.page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

        return True
