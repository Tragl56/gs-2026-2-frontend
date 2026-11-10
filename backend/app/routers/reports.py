"""Endpoints do cidadão: triagem, confirmação, consulta e avaliação de relatos."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.pipelines.triage import TriagePipeline, manual_title
from app.providers.llm import LLMError, LLMInvalidResponse
from app.providers.open_data import lookup_cep
from app.providers.repository import ReportRepository
from app.routers.deps import get_pipeline, get_repo, limit_analyze
from app.schemas.report import (
    CATEGORY_INFO,
    CategoryOut,
    Feedback,
    PublicRecord,
    Report,
    ReportCreate,
    ReportInput,
    TriageResult,
)

router = APIRouter(prefix="/api/v1", tags=["cidadão"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories() -> list[CategoryOut]:
    return [CategoryOut(value=c, **info) for c, info in CATEGORY_INFO.items()]


@router.post("/reports/analyze", response_model=TriageResult, dependencies=[Depends(limit_analyze)])
def analyze_report(
    data: ReportInput,
    request: Request,
    pipeline: TriagePipeline = Depends(get_pipeline),
    repo: ReportRepository = Depends(get_repo),
) -> TriageResult:
    """Etapa 1: a IA classifica o relato. Nada é salvo ainda (o cidadão confirma depois)."""
    try:
        result = pipeline.run(data)
    except LLMInvalidResponse:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={"code": "invalid_ai_response", "message": "A IA respondeu em formato inesperado."},
        )
    except LLMError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "llm_unavailable", "message": "O serviço de IA está indisponível."},
        )
    days = request.app.state.settings.similar_window_days
    similar = repo.count_similar_open(result.category, result.location, days)
    return result.model_copy(update={"similar_open": similar})


@router.post("/reports", response_model=Report, status_code=status.HTTP_201_CREATED)
def confirm_report(body: ReportCreate, repo: ReportRepository = Depends(get_repo)) -> Report:
    """Etapa 2 (human-in-the-loop): o cidadão confirma/corrige a triagem e gera o protocolo.

    Se a IA estiver fora do ar, `triage` vem vazio e o cidadão classifica sozinho:
    o relato não se perde.
    """
    info = CATEGORY_INFO[body.final_category]
    triage = body.triage
    if triage is not None:
        location = triage.location
        corrected = body.final_category != triage.category or body.final_urgency != triage.urgency
        title, summary = triage.title, triage.summary
    else:
        location = lookup_cep(body.input.cep) if body.input.cep else None
        corrected = False
        title = manual_title(body.input.description)
        summary = "Registrado pelo cidadão sem análise da IA."
    return repo.add({
        "description": body.input.description,
        "cep": body.input.cep,
        "reference": body.input.reference,
        "location": location,
        "ai_category": triage.category if triage else None,
        "ai_urgency": triage.urgency if triage else None,
        "final_category": body.final_category,
        "final_urgency": body.final_urgency,
        "corrected_by_citizen": corrected,
        "ai_used": triage is not None,
        "category_label": info["label"],
        "department": info["department"],
        "title": title,
        "summary": summary,
    })


@router.get("/reports", response_model=list[Report])
def my_reports(
    protocols: str = Query(..., max_length=2000, description="Protocolos separados por vírgula"),
    repo: ReportRepository = Depends(get_repo),
) -> list[Report]:
    """O cidadão só vê os relatos cujos protocolos ele possui (não há listagem pública)."""
    wanted = [p.strip() for p in protocols.split(",") if p.strip()]
    return repo.list(protocols=wanted)


@router.get("/stats/public", response_model=list[PublicRecord])
def public_stats(repo: ReportRepository = Depends(get_repo)) -> list[PublicRecord]:
    """Dados agregáveis para o painel da cidade: sem descrição, CEP ou referência."""
    return [
        PublicRecord(
            created_at=r.created_at,
            category=r.final_category,
            category_label=r.category_label,
            urgency=r.final_urgency,
            status=r.status,
            neighborhood=(r.location.neighborhood if r.location and r.location.neighborhood else "Não informado"),
            corrected_by_citizen=r.corrected_by_citizen,
            ai_used=r.ai_used,
        )
        for r in repo.list()
    ]


@router.patch("/reports/{protocol}/feedback", response_model=Report)
def give_feedback(protocol: str, body: Feedback, repo: ReportRepository = Depends(get_repo)) -> Report:
    report = repo.get_by_protocol(protocol)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Protocolo não encontrado."})
    return repo.update(report.model_copy(update={"feedback_useful": body.useful, "feedback_comment": body.comment}))
