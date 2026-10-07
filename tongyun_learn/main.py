import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tongyun_learn import __version__
from tongyun_learn.config import Settings, get_settings
from tongyun_learn.errors import register_error_handlers
from tongyun_learn.routers import ai, health, learn


def _setup_logging() -> None:
    log = logging.getLogger("tongyun_learn")
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()
    _setup_logging()

    app = FastAPI(
        title="tongyun-learn",
        version=__version__,
        root_path=settings.root_path,
        docs_url="/v1/docs" if settings.docs_enabled else None,
        openapi_url="/v1/openapi.json" if settings.docs_enabled else None,
        redoc_url=None,
    )

    register_error_handlers(app)

    if settings.cors_origins.strip():
        origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        if origins:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=origins,
                allow_credentials=True,
                allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type"],
            )

    app.include_router(health.router, prefix="/v1")
    app.include_router(ai.router, prefix="/v1")
    app.include_router(learn.router, prefix="/v1")
    app.get("/healthz", tags=["health"])(health.liveness)

    return app


app = create_app()
