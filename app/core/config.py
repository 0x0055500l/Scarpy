from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM Settings
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"

    # Browser Settings
    browser_headless: bool = True
    browser_timeout: int = 30000  # milliseconds
    browser_user_agent: Optional[str] = None
    browser_screenshots: bool = True
    browser_tracing: bool = False

    # Engine Settings
    max_retries: int = 3

    # Database Settings
    database_url: str = "sqlite+aiosqlite:///./test.db"

    # Logging Settings
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
