from fastapi import FastAPI

from agah.routers import auth


def create_app() -> FastAPI:
    app = FastAPI(title="آگاه API", version="0.1.0")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    return app


app = create_app()
