"""Endpoints do gestor (prefeitura): visão de todos os relatos e mudança de status."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.providers.repository import ReportRepository
from app.routers.deps import get_repo, require_manager
from app.schemas.report import Report, StatusUpdate

router = APIRouter(prefix="/api/v1/manager", tags=["gestor"], dependencies=[Depends(require_manager)])


@router.get("/reports", response_model=list[Report])
def all_reports(repo: ReportRepository = Depends(get_repo)) -> list[Report]:
    return repo.list()


@router.patch("/reports/{protocol}/status", response_model=Report)
def update_status(protocol: str, body: StatusUpdate, repo: ReportRepository = Depends(get_repo)) -> Report:
    report = repo.set_status(protocol, body.status, body.manager_note)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Protocolo não encontrado."})
    return report
