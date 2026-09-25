"""GLM 4.6 client for page-image recognition.

Uses the OpenAI-compatible endpoint exposed by Z.AI / BigModel, so the official
`openai` SDK is enough:

    OpenAI(api_key=..., base_url="https://api.z.ai/api/paas/v4/")

Model selection
---------------
Plain `glm-4.6` is text-only, so a *multimodal* member of the family is required
to feed page images.  `GLM_MODEL` is tried first, then every entry of
`GLM_MODEL_FALLBACKS`, and the first model the endpoint accepts wins.  All model
names come from configuration - nothing is hardcoded.

What is measured per the brief: wall-clock time from sending the request to
receiving the answer, and `usage.prompt_tokens / completion_tokens /
total_tokens` as reported by the API.
"""

from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import Settings
from app.schemas.document import (
    BlockType,
    DocumentJSON,
    DocumentPage,
    DocumentSource,
    DocumentType,
    make_image_block,
    make_table_block,
    make_text_block,
    renumber_blocks,
)
from app.schemas.recognition import PageRecognitionMeta, RecognitionMeta, TokenUsage
from app.services import prompts
from app.services.glm_payload import extract_json_payload, parse_model_answer
from app.services.images import ImageStore, clamp_bbox
from app.services.layout import sort_document_reading_order
from app.services.pdf_parser import RenderedPage, image_to_png_bytes


class GlmConfigurationError(RuntimeError):
    """No API key / unusable configuration."""


class GlmRequestError(RuntimeError):
    """Every configured model failed for this page."""


@dataclass
class RecognitionResult:
    document: DocumentJSON
    meta: RecognitionMeta
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #


def _to_data_uri(image_bytes: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _usage_from_response(response) -> TokenUsage:
    """Read `usage`, tolerating both OpenAI and native GLM field layouts."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return TokenUsage()

    def _get(obj, name: str) -> int:
        value = getattr(obj, name, None)
        if value is None and isinstance(obj, dict):
            value = obj.get(name)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    details = getattr(usage, "prompt_tokens_details", None) or {}
    completion_details = getattr(usage, "completion_tokens_details", None) or {}

    def _detail(container, name: str) -> int:
        if container is None:
            return 0
        value = getattr(container, name, None)
        if value is None and isinstance(container, dict):
            value = container.get(name)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    return TokenUsage(
        prompt_tokens=_get(usage, "prompt_tokens"),
        completion_tokens=_get(usage, "completion_tokens"),
        total_tokens=_get(usage, "total_tokens"),
        cached_tokens=_detail(details, "cached_tokens"),
        reasoning_tokens=_detail(completion_details, "reasoning_tokens"),
    )


def _message_text(response) -> str:
    try:
        message = response.choices[0].message
    except (AttributeError, IndexError, TypeError):
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some gateways return content parts
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(getattr(part, "text", "")))
        return "".join(parts)
    return ""


# --------------------------------------------------------------------------- #
#  client
# --------------------------------------------------------------------------- #


class Glm46Client:
    """Recognizes scanned pages with GLM 4.6 (multimodal)."""

    def __init__(self, settings: Settings, store: ImageStore) -> None:
        if not settings.api_key:
            raise GlmConfigurationError(
                "Не задан ключ GLM. Укажите GLM_API_KEY в файле .env "
                "(см. .env.example) или включите GLM_MOCK=true для офлайн-прогона."
            )
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise GlmConfigurationError(
                "Не установлен пакет openai (pip install -r requirements.txt)."
            ) from exc

        self.settings = settings
        self.store = store
        self._client = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.glm_base_url,
            timeout=settings.glm_timeout_seconds,
            max_retries=settings.glm_max_retries,
        )

    # -- single request ---------------------------------------------------- #
    async def _call_model(
        self,
        model: str,
        page: RenderedPage,
        document_type: DocumentType,
        *,
        repair_of: str | None = None,
    ) -> tuple[str, TokenUsage]:
        user_content: list[dict] = [
            {
                "type": "text",
                "text": prompts.build_page_prompt(
                    document_type, page.page_number, page.size
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": _to_data_uri(image_to_png_bytes(page.image))},
            },
        ]
        if repair_of:
            user_content.append(
                {"type": "text", "text": prompts.build_repair_prompt(repair_of)}
            )

        kwargs: dict = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": prompts.build_system_prompt(document_type),
                },
                {"role": "user", "content": user_content},
            ],
            "temperature": self.settings.glm_temperature,
            "max_tokens": self.settings.glm_max_tokens,
        }

        if self.settings.glm_json_mode:
            try:
                response = await self._client.chat.completions.create(
                    response_format={"type": "json_object"}, **kwargs
                )
            except Exception:
                # endpoint does not support structured output - retry plain
                response = await self._client.chat.completions.create(**kwargs)
        else:
            response = await self._client.chat.completions.create(**kwargs)

        return _message_text(response), _usage_from_response(response)

    # -- one page ---------------------------------------------------------- #
    async def _recognize_page(
        self,
        page: RenderedPage,
        document_type: DocumentType,
        session_id: str,
    ) -> tuple[DocumentPage, PageRecognitionMeta]:
        """Try every configured model, with one JSON-repair retry each."""
        candidates = self.settings.model_candidates
        warnings: list[str] = []
        last_error: str | None = None

        for position, model in enumerate(candidates):
            attempts = 0
            usage_total = TokenUsage()
            elapsed_total = 0.0
            repair_of: str | None = None

            for attempt in range(1, 3):
                attempts = attempt
                started = time.perf_counter()
                try:
                    content, usage = await asyncio.wait_for(
                        self._call_model(model, page, document_type, repair_of=repair_of),
                        timeout=self.settings.glm_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    last_error = (
                        f"{model}: превышен таймаут "
                        f"{self.settings.glm_timeout_seconds:.0f} c"
                    )
                    warnings.append(last_error)
                    break
                except Exception as exc:  # noqa: BLE001 - surfaced to the caller
                    last_error = f"{model}: {type(exc).__name__}: {exc}"
                    warnings.append(last_error)
                    break

                elapsed_total += time.perf_counter() - started
                usage_total = usage_total + usage

                payload = extract_json_payload(content)
                if payload is None:
                    repair_of = content
                    warnings.append(f"{model}: ответ не является JSON (попытка {attempt}).")
                    continue

                parsed = parse_model_answer(payload, document_type, page.size)
                warnings.extend(parsed.warnings)
                blocks = self._materialize_blocks(parsed, page, session_id, warnings)

                if not blocks and attempt == 1:
                    repair_of = content
                    warnings.append(f"{model}: блоки не извлечены, повторный запрос.")
                    continue

                page_json = DocumentPage(
                    page_number=page.page_number,
                    width=page.width,
                    height=page.height,
                    blocks=blocks,
                )
                return page_json, PageRecognitionMeta(
                    page_number=page.page_number,
                    model=model,
                    request_seconds=round(elapsed_total, 4),
                    usage=usage_total,
                    text_blocks=len(page_json.blocks_of(BlockType.text)),
                    table_blocks=len(page_json.blocks_of(BlockType.table)),
                    image_blocks=len(page_json.blocks_of(BlockType.image)),
                    raw_response_chars=len(content),
                    attempts=attempts,
                )

            if position < len(candidates) - 1:
                warnings.append(
                    f"Переключение на следующую модель после ошибки: {last_error}"
                )

        return (
            DocumentPage(page_number=page.page_number, blocks=[]),
            PageRecognitionMeta(
                page_number=page.page_number,
                model=candidates[-1] if candidates else "",
                request_seconds=0.0,
                attempts=2,
                error=last_error,
            ),
        )

    # -- blocks ------------------------------------------------------------ #
    def _materialize_blocks(
        self,
        parsed,
        page: RenderedPage,
        session_id: str,
        warnings: list[str],
    ) -> list:
        """Turn parsed model blocks into schema blocks.

        Text and table blocks are taken as-is.  Image blocks carry only a bbox:
        the picture is cropped straight out of the scanned page and stored as a
        file, so nothing about it is ever "recognized".
        """
        blocks: list = []
        for raw in parsed.blocks:
            if raw.type is BlockType.image:
                bbox = clamp_bbox(raw.bbox, page.size) if raw.bbox else None
                url = (
                    self.store.crop(
                        session_id,
                        page.image,
                        bbox,
                        tag=f"p{page.page_number}",
                    )
                    if bbox
                    else None
                )
                if not url:
                    warnings.append(
                        f"Стр. {page.page_number}: кроп изображения вне границ страницы."
                    )
                    continue
                blocks.append(
                    make_image_block(
                        url, bbox, page_size=page.size, source="crop"
                    )
                )
            elif raw.type is BlockType.table:
                blocks.append(
                    make_table_block(raw.rows, raw.bbox, source="glm")
                )
            else:
                blocks.append(
                    make_text_block(
                        raw.content,
                        raw.bbox,
                        page_size=page.size,
                        source="glm",
                    )
                )
        return blocks

    # -- whole document ---------------------------------------------------- #
    async def recognize_document(
        self,
        pages: list[RenderedPage],
        document_type: DocumentType,
        *,
        session_id: str,
    ) -> RecognitionResult:
        """Recognize every page and aggregate timing / token metadata."""
        started_at = datetime.now(timezone.utc)
        wall_start = time.perf_counter()

        doc_pages: list[DocumentPage] = []
        page_metas: list[PageRecognitionMeta] = []
        warnings: list[str] = []
        total_usage = TokenUsage()

        for page in pages:
            page_json, page_meta = await self._recognize_page(
                page, document_type, session_id
            )
            doc_pages.append(page_json)
            page_metas.append(page_meta)
            total_usage = total_usage + page_meta.usage
            if page_meta.error:
                warnings.append(
                    f"Стр. {page.page_number} не распознана: {page_meta.error}"
                )

        wall_elapsed = time.perf_counter() - wall_start
        finished_at = datetime.now(timezone.utc)

        document = DocumentJSON(
            document_type=document_type,
            source=DocumentSource.recognized,
            session_id=session_id,
            pages=doc_pages,
            model=page_metas[-1].model if page_metas else None,
            parser="glm",
        )
        sort_document_reading_order(document)
        renumber_blocks(document)

        used_models: list[str] = []
        for meta in page_metas:
            if meta.model and meta.model not in used_models:
                used_models.append(meta.model)

        recognition_meta = RecognitionMeta(
            session_id=session_id,
            model=used_models[-1] if used_models else self.settings.glm_model,
            requested_models=self.settings.model_candidates,
            fallback_models=used_models[1:] if len(used_models) > 1 else [],
            request_seconds=round(wall_elapsed, 4),
            usage=total_usage,
            pages=page_metas,
            render_dpi=self.settings.render_dpi,
            prompt_version=prompts.PROMPT_VERSION,
            started_at=started_at.isoformat(timespec="seconds"),
            finished_at=finished_at.isoformat(timespec="seconds"),
            warnings=warnings,
        )

        return RecognitionResult(
            document=document, meta=recognition_meta, warnings=warnings
        )

    async def aclose(self) -> None:
        await self._client.close()
