"""REST endpoints.

    GET    /api/health
    GET    /api/document-types
    POST   /api/upload            multipart: document_type + reference + recognized
    POST   /api/recognize         JSON: {session_id, model?, force?}
    POST   /api/metrics           JSON: {session_id, options, include_diff}
    GET    /api/results/{id}      everything the UI needs for one session
    GET    /api/sessions          recent sessions
    DELETE /api/results/{id}      remove a session and its files
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_image_store, get_session_store, get_settings_dep
from app.config import Settings
from app.schemas.api import (
    DocumentTypeInfo,
    DocumentTypeListResponse,
    MetricsRequest,
    MetricsResponse,
    RecognizeRequest,
    RecognizeResponse,
    ResultsResponse,
    SessionListResponse,
    SessionSummary,
    UploadedSide,
    UploadResponse,
)
from app.schemas.document import DocumentSource, DocumentType
from app.schemas.metrics import PerformanceMetrics
from app.schemas.session import SessionMeta
from app.services.glm_client import GlmConfigurationError
from app.services.glm_mock import build_glm_client
from app.services.images import ImageStore
from app.services.metrics import compute_metrics
from app.services.parsers import (
    parse_reference,
    render_recognized_pages,
    validate_upload,
)
from app.services.storage import SessionStore


router = APIRouter(prefix="/api", tags=["benchmark"])

REFERENCE_ROLE = "Эталон (файл А)"
RECOGNIZED_ROLE = "Распознаваемый (файл Б)"


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #


async def _read_upload(upload: UploadFile, limit_bytes: int) -> bytes:
    """Read an upload while enforcing the size cap (fails fast on huge files)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Файл «{upload.filename}» превышает лимит "
                    f"{limit_bytes / 1024 / 1024:.0f} МБ."
                ),
            )
        chunks.append(chunk)
    await upload.close()
    return b"".join(chunks)


def _summarize(meta: SessionMeta, metrics) -> SessionSummary:
    overall = metrics.overall if metrics else None
    performance = metrics.performance if metrics else None
    return SessionSummary(
        session_id=meta.session_id,
        document_type=meta.document_type,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
        reference_filename=meta.reference.filename if meta.reference else None,
        recognized_filename=meta.recognized.filename if meta.recognized else None,
        recognized_status="ready" if meta.recognized_json_ready else "pending",
        metrics_status="ready" if meta.metrics_ready else "pending",
        model=meta.model,
        cer=overall.cer if overall else None,
        wer=overall.wer if overall else None,
        exact_match=overall.exact_match if overall else None,
        request_seconds=performance.request_seconds if performance else None,
        total_tokens=performance.total_tokens if performance else None,
    )


def _document_type_or_400(value: str) -> DocumentType:
    try:
        return DocumentType(value)
    except ValueError as exc:
        allowed = ", ".join(t.value for t in DocumentType)
        raise HTTPException(
            status_code=422,
            detail=f"Неизвестный тип документа «{value}». Допустимо: {allowed}.",
        ) from exc


# --------------------------------------------------------------------------- #
#  meta endpoints
# --------------------------------------------------------------------------- #


@router.get("/health")
def health(settings: Settings = Depends(get_settings_dep)) -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "model": settings.glm_model,
        "model_chain": settings.model_candidates,
        "base_url": settings.glm_base_url,
        "api_key_configured": bool(settings.api_key),
        "mock_mode": settings.glm_mock,
        "render_dpi": settings.render_dpi,
        "max_upload_mb": settings.max_upload_mb,
    }


@router.get("/document-types", response_model=DocumentTypeListResponse)
def document_types(
    settings: Settings = Depends(get_settings_dep),
) -> DocumentTypeListResponse:
    allowed = ", ".join(sorted(settings.allowed_suffixes)).upper()
    return DocumentTypeListResponse(
        document_types=[
            DocumentTypeInfo(
                id=document_type,
                label=document_type.label,
                description=document_type.description,
                entities=document_type.entity_set,
                accepted_hint=f"{allowed}, до {settings.max_upload_mb} МБ",
            )
            for document_type in DocumentType
        ],
        default=DocumentType.text_tables_images,
    )


# --------------------------------------------------------------------------- #
#  POST /api/upload
# --------------------------------------------------------------------------- #


@router.post("/upload", response_model=UploadResponse)
async def upload(
    document_type: str = Form(
        ..., description="text_only | text_tables | text_tables_images"
    ),
    reference: UploadFile = File(..., description="Файл А: эталон с текстовым слоем"),
    recognized: UploadFile = File(..., description="Файл Б: скан без текстового слоя"),
    settings: Settings = Depends(get_settings_dep),
    store: SessionStore = Depends(get_session_store),
    images: ImageStore = Depends(get_image_store),
) -> UploadResponse:
    """Store the pair, extract the reference JSON, validate file B."""
    doc_type = _document_type_or_400(document_type)

    reference_blob = await _read_upload(reference, settings.max_upload_bytes)
    recognized_blob = await _read_upload(recognized, settings.max_upload_bytes)

    reference_probe = validate_upload(
        reference.filename or "reference", reference_blob, settings, role=REFERENCE_ROLE
    )
    recognized_probe = validate_upload(
        recognized.filename or "recognized",
        recognized_blob,
        settings,
        role=RECOGNIZED_ROLE,
    )

    meta = store.create(doc_type)
    session_id = meta.session_id
    upload_warnings: list[str] = []

    # ---- file A --------------------------------------------------------- #
    reference_info = store.save_upload(
        session_id,
        "reference",
        reference.filename or f"reference{reference_probe.suffix}",
        reference_blob,
        reference_probe.suffix,
    )
    reference_info.mime_type = reference_probe.mime_type
    reference_info.page_count = reference_probe.page_count
    reference_info.has_text_layer = reference_probe.has_text_layer
    reference_info.text_layer_chars = reference_probe.text_layer_chars
    reference_info.render_backend = settings.renderer_backend

    if reference_probe.text_layer_chars == 0:
        upload_warnings.append(
            "Внимание: в эталонном файле не найден текстовый слой, "
            "извлечение даст пустой эталон."
        )

    reference_result = parse_reference(
        reference_info.stored_path,
        document_type=doc_type,
        session_id=session_id,
        store=images,
        settings=settings,
        suffix=reference_probe.suffix,
    )
    upload_warnings.extend(reference_result.warnings)
    store.save_document(reference_result.document)
    if reference_result.rendered_pages:
        store.save_page_renders(
            session_id, "reference", reference_result.rendered_pages
        )

    # ---- file B --------------------------------------------------------- #
    recognized_info = store.save_upload(
        session_id,
        "recognized",
        recognized.filename or f"recognized{recognized_probe.suffix}",
        recognized_blob,
        recognized_probe.suffix,
    )
    recognized_info.mime_type = recognized_probe.mime_type
    recognized_info.page_count = recognized_probe.page_count
    recognized_info.has_text_layer = recognized_probe.has_text_layer
    recognized_info.text_layer_chars = recognized_probe.text_layer_chars
    recognized_info.render_backend = settings.renderer_backend

    recognized_warnings: list[str] = []
    if recognized_probe.suffix != ".pdf":
        recognized_warnings.append(
            "Файл Б должен быть PDF-сканом: GLM получает изображения страниц, "
            "DOCX нельзя растрировать. Конвертируйте файл в PDF."
        )
    if recognized_probe.has_text_layer:
        recognized_warnings.append(
            "В файле Б обнаружен текстовый слой "
            f"({recognized_probe.text_layer_chars} симв.). Ожидается распечатанный "
            "и подписанный скан без текстового слоя - результат распознавания "
            "может быть некорректным."
        )

    meta.reference = reference_info
    meta.recognized = recognized_info
    meta.reference_json_ready = True
    meta.warnings = upload_warnings + recognized_warnings
    store.write_meta(meta)

    return UploadResponse(
        session_id=session_id,
        document_type=doc_type,
        reference=UploadedSide(
            role="reference",
            file=reference_info,
            document=reference_result.document,
            ready=True,
            warnings=reference_result.warnings,
        ),
        recognized=UploadedSide(
            role="recognized",
            file=recognized_info,
            document=None,
            ready=False,
            warnings=recognized_warnings,
        ),
        warnings=meta.warnings,
    )


# --------------------------------------------------------------------------- #
#  POST /api/recognize
# --------------------------------------------------------------------------- #


@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(
    payload: RecognizeRequest,
    settings: Settings = Depends(get_settings_dep),
    store: SessionStore = Depends(get_session_store),
    images: ImageStore = Depends(get_image_store),
) -> RecognizeResponse:
    """Send every page of file B to GLM 4.6 and build `recognized.json`."""
    meta = store.read_meta(payload.session_id)
    if meta.recognized is None:
        raise HTTPException(status_code=409, detail="Файл Б не загружен.")
    if meta.recognized_json_ready and not payload.force:
        existing = store.load_document(payload.session_id, DocumentSource.recognized)
        recognition = store.load_recognition(payload.session_id)
        if existing and recognition:
            return RecognizeResponse(
                session_id=payload.session_id,
                document_type=meta.document_type,
                model=recognition.model,
                document=existing,
                meta=recognition,
                warnings=recognition.warnings,
            )

    upload_path = store.upload_path(payload.session_id, "recognized")
    if upload_path is None:
        raise HTTPException(status_code=409, detail="Файл Б не найден на диске.")

    suffix = upload_path.suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(
            status_code=422,
            detail=(
                "Распознаваемый документ отправляется в GLM как изображения "
                "страниц, поэтому файл Б должен быть PDF-сканом. "
                "Конвертируйте DOCX в PDF."
            ),
        )

    pages = render_recognized_pages(upload_path, settings, suffix)
    if not pages:
        raise HTTPException(status_code=422, detail="PDF не содержит страниц.")

    store.save_page_renders(payload.session_id, "recognized", pages)

    run_settings = (
        settings.model_copy(update={"glm_model": payload.model})
        if payload.model
        else settings
    )
    client = build_glm_client(run_settings, images)

    try:
        result = await client.recognize_document(
            pages, meta.document_type, session_id=payload.session_id
        )
    except GlmConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await client.aclose()

    store.save_document(result.document)
    store.save_recognition(result.meta)

    meta.recognized_json_ready = True
    meta.metrics_ready = False
    meta.model = result.meta.model
    meta.warnings = list(dict.fromkeys(meta.warnings + result.warnings))
    store.write_meta(meta)
    # a re-run invalidates the previous metrics report
    store.delete_metrics(payload.session_id)

    return RecognizeResponse(
        session_id=payload.session_id,
        document_type=meta.document_type,
        model=result.meta.model,
        document=result.document,
        meta=result.meta,
        warnings=result.warnings,
    )


# --------------------------------------------------------------------------- #
#  POST /api/metrics
# --------------------------------------------------------------------------- #


@router.post("/metrics", response_model=MetricsResponse)
def metrics(
    payload: MetricsRequest,
    store: SessionStore = Depends(get_session_store),
) -> MetricsResponse:
    """CER / WER / exact success + timing and token accounting."""
    meta = store.read_meta(payload.session_id)
    reference = store.load_document(payload.session_id, DocumentSource.reference)
    recognized = store.load_document(payload.session_id, DocumentSource.recognized)

    missing = []
    if reference is None:
        missing.append("эталонный JSON")
    if recognized is None:
        missing.append("распознанный JSON")
    if missing:
        raise HTTPException(
            status_code=409,
            detail=(
                "Метрики пока недоступны: не сформирован "
                + " и ".join(missing)
                + ". Сначала загрузите пару и запустите распознавание."
            ),
        )

    if not payload.recompute:
        cached = store.load_metrics(payload.session_id)
        if cached is not None:
            return MetricsResponse(
                session_id=payload.session_id,
                document_type=meta.document_type,
                report=cached,
            )

    recognition = store.load_recognition(payload.session_id)
    performance = PerformanceMetrics()
    if recognition is not None:
        performance = PerformanceMetrics(
            model=recognition.model,
            request_seconds=recognition.request_seconds,
            prompt_tokens=recognition.usage.prompt_tokens,
            completion_tokens=recognition.usage.completion_tokens,
            total_tokens=recognition.usage.total_tokens,
            cached_tokens=recognition.usage.cached_tokens,
            reasoning_tokens=recognition.usage.reasoning_tokens,
            pages_processed=len(recognition.pages),
            per_page_seconds=[p.request_seconds for p in recognition.pages],
            retries=sum(max(0, p.attempts - 1) for p in recognition.pages),
            fallback_models=recognition.fallback_models,
        )

    report = compute_metrics(
        reference,
        recognized,
        payload.options,
        performance=performance,
        include_diff=payload.include_diff,
    )
    store.save_metrics(report)

    meta.metrics_ready = True
    store.write_meta(meta)

    return MetricsResponse(
        session_id=payload.session_id,
        document_type=meta.document_type,
        report=report,
    )


# --------------------------------------------------------------------------- #
#  GET /api/results/{session_id}
# --------------------------------------------------------------------------- #


@router.get("/results/{session_id}", response_model=ResultsResponse)
def results(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> ResultsResponse:
    """Everything about one session - used to restore the UI state."""
    meta = store.read_meta(session_id)

    reference = store.load_document(session_id, DocumentSource.reference)
    recognized = store.load_document(session_id, DocumentSource.recognized)
    recognition = store.load_recognition(session_id)
    metrics_report = store.load_metrics(session_id)

    reference_ready = reference is not None
    recognized_ready = recognized is not None
    metrics_ready = metrics_report is not None and reference_ready and recognized_ready

    return ResultsResponse(
        session=_summarize(meta, metrics_report),
        reference_file=meta.reference,
        recognized_file=meta.recognized,
        reference=reference,
        recognized=recognized,
        recognition=recognition,
        metrics=metrics_report,
        warnings=meta.warnings,
        reference_json_ready=reference_ready,
        recognized_json_ready=recognized_ready,
        metrics_ready=metrics_ready,
    )


@router.get("/sessions", response_model=SessionListResponse)
def sessions(store: SessionStore = Depends(get_session_store)) -> SessionListResponse:
    summaries = [
        _summarize(meta, store.load_metrics(meta.session_id))
        for meta in store.list_sessions()
    ]
    return SessionListResponse(sessions=summaries)


@router.delete("/results/{session_id}")
def delete_results(
    session_id: str, store: SessionStore = Depends(get_session_store)
) -> dict:
    store.read_meta(session_id)  # 404 when unknown
    store.delete_session(session_id)
    return {"deleted": session_id}
