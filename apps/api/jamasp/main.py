from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jamasp.config import get_settings
from jamasp.routers import (
    auth,
    entities,
    knowledge,
    overview,
    query,
    reports,
    scans,
    settings,
    sources,
)


def create_app() -> FastAPI:
    app = FastAPI(title="جاماسپ API", version="0.1.0")

    # allow_credentials with an explicit origin list: the session cookie will not
    # travel with a wildcard origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(sources.router)
    app.include_router(scans.router)
    app.include_router(entities.router)
    app.include_router(settings.router)
    app.include_router(knowledge.router)
    app.include_router(query.router)
    app.include_router(reports.router)
    app.include_router(overview.router)
    return app


app = create_app()
