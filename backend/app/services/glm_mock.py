"""Offline stand-in for the GLM client (`GLM_MOCK=true`).

Purpose: exercise the whole upload -> recognize -> metrics flow and the UI
without spending tokens or even having a key.  The produced text is a stub, so
metrics from a mock run must never be reported as benchmark results - the UI and
the API both flag it.
"""

from __future__ import annotations

import asyncio
import time
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
from app.services.glm_client import Glm46Client, RecognitionResult
from app.services.images import ImageStore
from app.services.layout import sort_document_reading_order
from app.services.pdf_parser import RenderedPage, image_to_png_bytes

MOCK_MODEL = "mock-glm-4.6v"
MOCK_NOTE = (
    "Заглушка GLM_MOCK: текст не распознан. "
    "Задайте GLM_API_KEY в .env и выключите GLM_MOCK для реального бенчмарка."
)


def _count(blocks: list, block_type: BlockType) -> int:
    return len([b for b in blocks if b.type is block_type])


class MockGlmClient:
    """Deterministic fake with the same interface as :class:`Glm46Client`."""

    def __init__(self, settings: Settings, store: ImageStore) -> None:
        self.settings = settings
        self.store = store

    async def recognize_document(
        self,
        pages: list[RenderedPage],
        document_type: DocumentType,
        *,
        session_id: str,
    ) -> RecognitionResult:
        started_at = datetime.now(timezone.utc)
        wall_start = time.perf_counter()

        entity_set = document_type.entity_set
        doc_pages: list[DocumentPage] = []
        page_metas: list[PageRecognitionMeta] = []
        total_usage = TokenUsage()

        for page in pages:
            await asyncio.sleep(0.05)  # simulate latency

            blocks: list = [
                make_text_block(
                    f"{MOCK_NOTE} Страница {page.page_number}.",
                    bbox=[40.0, 40.0, float(page.width) - 80.0, 60.0],
                    page_size=page.size,
                    source="mock",
                )
            ]

            if entity_set.tables:
                blocks.append(
                    make_table_block(
                        [
                            ["Показатель", "Значение"],
                            ["mock-1", "0"],
                            ["mock-2", "0"],
                        ],
                        bbox=[40.0, 140.0, min(600.0, float(page.width) - 80.0), 120.0],
                        source="mock",
                    )
                )

            if entity_set.images:
                bbox = [
                    round(page.width * 0.2, 2),
                    round(page.height * 0.5, 2),
                    round(page.width * 0.6, 2),
                    round(page.height * 0.2, 2),
                ]
                url = self.store.crop(
                    session_id, page.image, bbox, tag=f"mock-p{page.page_number}"
                )
                if url:
                    blocks.append(
                        make_image_block(url, bbox, page_size=page.size, source="crop")
                    )

            doc_pages.append(
                DocumentPage(
                    page_number=page.page_number,
                    width=page.width,
                    height=page.height,
                    blocks=blocks,
                )
            )

            image_bytes = len(image_to_png_bytes(page.image))
            usage = TokenUsage(
                prompt_tokens=600 + image_bytes // 4000,
                completion_tokens=180,
                total_tokens=780 + image_bytes // 4000,
            )
            total_usage = total_usage + usage
            page_metas.append(
                PageRecognitionMeta(
                    page_number=page.page_number,
                    model=MOCK_MODEL,
                    request_seconds=0.05,
                    usage=usage,
                    text_blocks=_count(blocks, BlockType.text),
                    table_blocks=_count(blocks, BlockType.table),
                    image_blocks=_count(blocks, BlockType.image),
                    raw_response_chars=len(MOCK_NOTE),
                )
            )

        wall_elapsed = time.perf_counter() - wall_start
        finished_at = datetime.now(timezone.utc)

        document = DocumentJSON(
            document_type=document_type,
            source=DocumentSource.recognized,
            session_id=session_id,
            pages=doc_pages,
            model=MOCK_MODEL,
            parser="mock",
        )
        sort_document_reading_order(document)
        renumber_blocks(document)

        warning = (
            "GLM_MOCK=true: распознавание выполнено заглушкой, "
            "метрики не отражают качество GLM 4.6."
        )
        meta = RecognitionMeta(
            session_id=session_id,
            model=MOCK_MODEL,
            requested_models=[MOCK_MODEL],
            request_seconds=round(wall_elapsed, 4),
            usage=total_usage,
            pages=page_metas,
            render_dpi=self.settings.render_dpi,
            started_at=started_at.isoformat(timespec="seconds"),
            finished_at=finished_at.isoformat(timespec="seconds"),
            warnings=[warning],
        )
        return RecognitionResult(document=document, meta=meta, warnings=[warning])

    async def aclose(self) -> None:
        return None


def build_glm_client(settings: Settings, store: ImageStore):
    """Return the mock or the real client depending on configuration."""
    if settings.glm_mock:
        return MockGlmClient(settings, store)
    return Glm46Client(settings, store)
