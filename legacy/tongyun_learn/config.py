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
    # 云芽英语教练。只认 DeepSeek，不走 KIE。无 key 时规则降级。
    deepseek_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("DEEPSEEK_API_KEY", "LEARN_DEEPSEEK_API_KEY"),
    )
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # 手敲判分：默认忽略大小写。例句阶段另外忽略标点。
    type_ignore_case: bool = True
    tz: str = "Asia/Shanghai"
    # 接口文档 /v1/docs、/v1/openapi.json：生产默认关闭，本机调试设 LEARN_DOCS_ENABLED=true
    docs_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
