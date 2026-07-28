from pydantic import BaseModel, field_validator

from agah.llm.router import DEFAULT_ROUTES

REDACTED = "••••••••"


class ProviderConfig(BaseModel):
    base_url: str
    api_key: str = ""
    extra_headers: dict[str, str] | None = None


class ProvidersUpdate(BaseModel):
    providers: dict[str, ProviderConfig]


class RouteConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.2
    fallbacks: list[tuple[str, str]] = []


class RoutesUpdate(BaseModel):
    routes: dict[str, RouteConfig]

    @field_validator("routes")
    @classmethod
    def reject_unknown_tasks(cls, value: dict[str, RouteConfig]) -> dict[str, RouteConfig]:
        unknown = sorted(value.keys() - DEFAULT_ROUTES.keys())
        if unknown:
            raise ValueError(
                f"unknown LLM tasks: {unknown}. Known tasks: {sorted(DEFAULT_ROUTES)}"
            )
        return value


class LLMSettingsOut(BaseModel):
    providers: dict[str, ProviderConfig]
    routes: dict[str, RouteConfig]
