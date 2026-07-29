from fastapi import FastAPI

from agah.routers import auth, entities, knowledge, query, scans, settings, sources


def create_app() -> FastAPI:
    app = FastAPI(title="آگاه API", version="0.1.0")

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
    return app


app = create_app()
