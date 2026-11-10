"""Ponto de entrada da API Zela (FastAPI)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.pipelines.triage import TriagePipeline
from app.providers.llm import LLMError, build_provider
from app.providers.rate_limit import RateLimiter
from app.providers.repository import ReportRepository
from app.providers.seed import seed_if_empty
from app.routers import health, manager, reports

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("zela")


def create_app(settings: Settings | None = None, repo: ReportRepository | None = None,
               pipeline: TriagePipeline | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.limiter = RateLimiter(settings.analyze_rate_limit_per_minute)
        app.state.repo = repo or ReportRepository(settings.database_path)
        if settings.seed_demo_data:
            seed_if_empty(app.state.repo)
        if pipeline is not None:
            app.state.pipeline = pipeline
        else:
            try:
                app.state.pipeline = TriagePipeline(build_provider(settings))
            except LLMError as exc:
                log.error("IA indisponível: %s", exc)
                app.state.pipeline = None
        yield

    app = FastAPI(title="Zela API", version="1.1.0", lifespan=lifespan,
                  description="Triagem de relatos urbanos com IA")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Manager-Token"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # Mensagens simples para o cidadão, sem stack trace.
        messages = [str(e.get("msg", "")).removeprefix("Value error, ") for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": {"code": "invalid_input", "message": " ".join(messages)}})

    app.include_router(health.router)
    app.include_router(reports.router)
    app.include_router(manager.router)
    return app


app = create_app()
