import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import chat, health, voice
from app.core.config import get_settings
from app.core.errors import ConfigurationError, ProviderError, RateLimitError
from app.core.ratelimit import RequestGuard

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="DocQuest Voice")
    app.state.guard = RequestGuard(settings.rate_limit_per_minute, settings.daily_request_cap)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ConfigurationError)
    async def _configuration_error(_: Request, exc: ConfigurationError) -> JSONResponse:
        logger.error("Configuration error: %s", exc)
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def _provider_error(_: Request, exc: ProviderError) -> JSONResponse:
        logger.error("Provider error: %s", exc, exc_info=exc)
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(RateLimitError)
    async def _rate_limit_error(_: Request, exc: RateLimitError) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": str(exc)},
            headers={"Retry-After": str(max(1, int(exc.retry_after)))},
        )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(voice.router)
    return app


app = create_app()
