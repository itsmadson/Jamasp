from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AGAH_", extra="ignore")

    database_url: str = "postgresql+asyncpg://agah:agah@localhost:5432/agah"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = ""
    jwt_secret: str = ""
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
