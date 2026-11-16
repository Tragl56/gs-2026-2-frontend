"""Endpoints de visão computacional: foto do cidadão (triagem de fissuras) e monitoramento da prefeitura."""
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.routers.deps import limit_analyze, require_manager
from app.schemas.vision import MonitorResult, SequenceResult, VisionResult
from app.vision.service import VisionInputError, VisionService

router = APIRouter(prefix="/api/v1/vision", tags=["visão computacional"])

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}


def get_vision(request: Request) -> VisionService:
    vision = getattr(request.app.state, "vision", None)
    if vision is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "vision_unavailable", "message": "A análise de imagens não está disponível neste servidor."},
        )
    return vision


async def _read(file: UploadFile, max_mb: int, kinds: set[str] | None = None) -> bytes:
    if kinds and file.content_type not in kinds:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail={"code": "invalid_input", "message": "Envie uma foto JPG, PNG ou WEBP."})
    data = await file.read(max_mb * 1024 * 1024 + 1)
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail={"code": "invalid_input", "message": f"Arquivo maior que {max_mb} MB."})
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail={"code": "invalid_input", "message": "Arquivo vazio."})
    return data


def _bad_input(exc: VisionInputError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "invalid_input", "message": str(exc)})


@router.get("/info")
def vision_info(vision: VisionService = Depends(get_vision)) -> dict:
    """Modelo em uso, dispositivo e limiar de triagem."""
    return vision.info()


@router.post("/inspect", response_model=VisionResult, dependencies=[Depends(limit_analyze)])
async def inspect_photo(request: Request, file: UploadFile = File(...), vision: VisionService = Depends(get_vision)) -> VisionResult:
    """Foto do cidadão: indica se há possível fissura, onde está e com que confiança. Nada é salvo aqui."""
    data = await _read(file, request.app.state.settings.vision_max_image_mb, IMAGE_TYPES)
    try:
        return await run_in_threadpool(vision.inspect, data)
    except VisionInputError as exc:
        raise _bad_input(exc)


@router.post("/sequence", response_model=SequenceResult, dependencies=[Depends(require_manager)])
async def inspect_sequence(request: Request, files: list[UploadFile] = File(...),
                           vision: VisionService = Depends(get_vision)) -> SequenceResult:
    """Prefeitura: sequência de fotos (ex.: câmera de vistoria) analisada em lote."""
    if len(files) > 40:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail={"code": "invalid_input", "message": "Envie no máximo 40 fotos por vez."})
    max_mb = request.app.state.settings.vision_max_image_mb
    payload = [(f.filename or "foto", await _read(f, max_mb, IMAGE_TYPES)) for f in files]
    return await run_in_threadpool(vision.sequence, payload)


@router.post("/monitor", response_model=MonitorResult, dependencies=[Depends(require_manager)])
async def monitor_video(request: Request, file: UploadFile = File(...),
                        every: int = Query(1, ge=1, le=10, description="Analisa 1 a cada N quadros"),
                        vision: VisionService = Depends(get_vision)) -> MonitorResult:
    """Prefeitura: vídeo curto (viatura, drone, celular) processado quadro a quadro, com alertas."""
    data = await _read(file, request.app.state.settings.vision_max_video_mb)
    try:
        return await run_in_threadpool(vision.monitor, data, every)
    except VisionInputError as exc:
        raise _bad_input(exc)
