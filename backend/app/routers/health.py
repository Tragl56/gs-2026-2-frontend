from fastapi import APIRouter, Request

router = APIRouter(tags=["infra"])


@router.get("/")
def root() -> dict:
    return {"servico": "Zela API", "documentacao": "/docs", "status": "/health"}


@router.get("/health")
def health(request: Request) -> dict:
    return {"status": "ok", "ai_ready": request.app.state.pipeline is not None}
