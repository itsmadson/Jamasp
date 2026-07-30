from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="JAMASP_", extra="ignore")

    database_url: str = "postgresql+asyncpg://jamasp:jamasp@localhost:5432/jamasp"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = ""
    jwt_secret: str = ""
    environment: str = "development"
    # Browsers block cross-origin XHR without these. Explicit origins, never "*":
    # credentials are not allowed with a wildcard.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Probing for undeclared foreign keys is expensive on a remote database and
    # only pays off on schemas that declare none. Off unless asked for.
    infer_relationships: bool = False

    # LLM providers. Stored settings override these at runtime; they exist so a
    # deployment can be configured entirely from .env with no UI step.
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""
    gapgpt_base_url: str = "https://api.gapgpt.app/v1"
    gapgpt_api_key: str = ""
    local_base_url: str = "http://localhost:11434/v1"
    local_api_key: str = ""

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def provider_defaults(self) -> dict[str, dict[str, str]]:
        return {
            "openrouter": {
                "base_url": self.openrouter_base_url,
                "api_key": self.openrouter_api_key,
            },
            "gapgpt": {"base_url": self.gapgpt_base_url, "api_key": self.gapgpt_api_key},
            "local": {"base_url": self.local_base_url, "api_key": self.local_api_key},
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
