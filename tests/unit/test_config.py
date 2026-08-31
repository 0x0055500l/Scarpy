import os

from app.core.config import Settings


def test_settings_load_from_env() -> None:
    # Set fake environment variables
    os.environ["LLM_PROVIDER"] = "anthropic"
    os.environ["BROWSER_HEADLESS"] = "false"

    settings = Settings()

    assert settings.llm_provider == "anthropic"
    assert settings.browser_headless is False

    # Cleanup
    del os.environ["LLM_PROVIDER"]
    del os.environ["BROWSER_HEADLESS"]
