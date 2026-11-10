"""Dependências compartilhadas pelos routers (injeção via FastAPI Depends)."""
import secrets

from fastapi import Header, HTTPException, Request, status

from app.config import get_settings
from app.pipelines.triage import TriagePipeline
from app.providers.repository import ReportRepository


def get_repo(request: Request) -> ReportRepository:
    return request.app.state.repo


def get_pipeline(request: Request) -> TriagePipeline:
    pipeline = request.app.state.pipeline
    if pipeline is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "llm_unavailable", "message": "Serviço de IA não configurado."},
        )
    return pipeline


def limit_analyze(request: Request) -> None:
    """Limita chamadas ao LLM por IP (protege a cota e evita abuso)."""
    ip = request.client.host if request.client else "desconhecido"
    if not request.app.state.limiter.allow(ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Muitas análises seguidas. Aguarde um minuto."},
        )


def require_manager(x_manager_token: str = Header(default="")) -> None:
    expected = get_settings().manager_token
    if not x_manager_token or not secrets.compare_digest(x_manager_token, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Acesso restrito à equipe da prefeitura."},
        )
