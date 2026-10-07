from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEARN_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "sqlite:///./dev.db"
    root_path: str = "/learn/api"
    cors_origins: str = ""
    token_web_sha256: str = ""
    token_axue_sha256: str = ""
    rate_web_per_min: int = 60
    rate_axue_per_min: int = 120
    ai_daily_web: int = 200
    ai_daily_axue: int = 500
    ai_model: str = "gemini-3-8-flash-openai"
    ai_fallback_model: str = "deepseek-v4-1-flash"
    ai_timeout_s: float = 30.0
    ai_total_budget_s: float = 50.0
    kie_base_url: str = "https://api.kie.ai"
    kie_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("KIE_API_KEY", "LEARN_KIE_API_KEY"),
    )
    tz: str = "Asia/Shanghai"


@lru_cache
def get_settings() -> Settings:
    return Settings()
