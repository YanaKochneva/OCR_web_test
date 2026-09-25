"""The unified document JSON schema.

Reference (file A) and recognized (file B) documents are stored as **separate**
documents that share this exact shape.  They are only ever joined - never
merged - later, inside the metrics stage.

    {
      "document_type": "text_tables_images",
      "source": "reference",
      "pages": [
        {
          "page_number": 1,
          "blocks": [
            {"type": "text",  "content": "..."},
            {"type": "table", "rows": [["a", "b"], ["c", "d"]]},
            {"type": "image", "url": "/static/images/<session>/<hash>.png",
             "bbox": [x, y, w, h]}
          ]
        }
      ]
    }
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field, field_validator

# --------------------------------------------------------------------------- #
#  enums
# --------------------------------------------------------------------------- #


class DocumentType(str, Enum):
    """The three fixed benchmark categories."""

    text_only = "text_only"
    text_tables = "text_tables"
    text_tables_images = "text_tables_images"

    @property
    def label(self) -> str:
        return {
            DocumentType.text_only: "Только текст",
            DocumentType.text_tables: "Текст + таблицы",
            DocumentType.text_tables_images: "Текст + таблицы + изображения",
        }[self]

    @property
    def description(self) -> str:
        return {
            DocumentType.text_only: (
                "Документ без таблиц и рисунков. Метрики считаются "
                "исключительно по текстовому слою."
            ),
            DocumentType.text_tables: (
                "Текст и табличные данные. Ячейки таблиц нормализуются в "
                "строки и участвуют в CER/WER наравне с текстом."
            ),
            DocumentType.text_tables_images: (
                "Текст, таблицы и изображения/схемы. Изображения "
                "сохраняются как кропы страницы и в метрики не входят."
            ),
        }[self]

    @property
    def entity_set(self) -> "EntitySet":
        return {
            DocumentType.text_only: EntitySet(text=True, tables=False, images=False),
            DocumentType.text_tables: EntitySet(text=True, tables=True, images=False),
            DocumentType.text_tables_images: EntitySet(
                text=True, tables=True, images=True
            ),
        }[self]


class DocumentSource(str, Enum):
    reference = "reference"
    recognized = "recognized"


class BlockType(str, Enum):
    text = "text"
    table = "table"
    image = "image"


class EntitySet(BaseModel):
    """Which entity kinds are *extracted* for a given document type."""

    text: bool = True
    tables: bool = False
    images: bool = False

    @property
    def metric_entities(self) -> list[str]:
        """Entities that feed CER/WER (images never do)."""
        entities = []
        if self.text:
            entities.append("text")
        if self.tables:
            entities.append("tables")
        return entities


# --------------------------------------------------------------------------- #
#  blocks
# --------------------------------------------------------------------------- #

BBox4 = list[float]  # [x, y, w, h] in page-pixel coordinates


class DocumentBlock(BaseModel):
    """One content block.  Only the fields relevant to `type` are populated."""

    id: str = ""
    type: BlockType

    # text
    content: str | None = None
    # table - rows of cells, always rectangular after normalization
    rows: list[list[str]] | None = None
    # image - URL of the crop stored on disk
    url: str | None = None
    caption: str | None = None

    # geometry: [x, y, w, h] in pixels of the reference/rendered page
    bbox: BBox4 | None = None
    # page-pixel size the bbox was measured against (for lossless re-scaling)
    page_size: list[int] | None = None

    # provenance / debugging
    confidence: float | None = None
    source: str | None = None  # "pymupdf" | "python-docx" | "glm" | "crop"

    @field_validator("rows")
    @classmethod
    def _rectangular(cls, rows: list[list[str]] | None) -> list[list[str]] | None:
        if not rows:
            return rows
        width = max(len(r) for r in rows)
        return [list(r) + [""] * (width - len(r)) for r in rows]

    @field_validator("bbox")
    @classmethod
    def _bbox_len(cls, bbox: BBox4 | None) -> BBox4 | None:
        if bbox is None:
            return None
        if len(bbox) != 4:
            raise ValueError("bbox must contain exactly 4 numbers [x, y, w, h]")
        return [round(float(v), 2) for v in bbox]

    # -- helpers ---------------------------------------------------------- #
    @property
    def metric_text(self) -> str:
        """Text contributed by this block to CER/WER (empty for images)."""
        if self.type is BlockType.text:
            return (self.content or "").strip()
        if self.type is BlockType.table:
            rows = self.rows or []
            return "\n".join(
                " | ".join((cell or "").strip() for cell in row) for row in rows
            )
        return ""


class TextBlock(DocumentBlock):
    type: Literal[BlockType.text] = BlockType.text


class TableBlock(DocumentBlock):
    type: Literal[BlockType.table] = BlockType.table


class ImageBlock(DocumentBlock):
    type: Literal[BlockType.image] = BlockType.image


# --------------------------------------------------------------------------- #
#  pages / document
# --------------------------------------------------------------------------- #


class DocumentPage(BaseModel):
    page_number: int = Field(ge=1)
    width: int | None = None
    height: int | None = None
    blocks: list[DocumentBlock] = Field(default_factory=list)

    def blocks_of(self, block_type: BlockType) -> list[DocumentBlock]:
        return [b for b in self.blocks if b.type is block_type]

    def metric_text(self) -> str:
        return "\n".join(t for t in (b.metric_text for b in self.blocks) if t)


class FileInfo(BaseModel):
    """Metadata about an uploaded file."""

    filename: str
    stored_path: str
    size_bytes: int
    extension: str
    mime_type: str
    sha256: str
    page_count: int | None = None
    has_text_layer: bool | None = None
    text_layer_chars: int | None = None
    render_backend: str | None = None


class DocumentJSON(BaseModel):
    """A fully materialized document (reference or recognized)."""

    document_type: DocumentType
    source: DocumentSource
    session_id: str
    pages: list[DocumentPage] = Field(default_factory=list)
    model: str | None = None
    parser: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    # -- construction helpers --------------------------------------------- #
    @property
    def entity_set(self) -> EntitySet:
        return self.document_type.entity_set

    def iter_blocks(self) -> Iterable[DocumentBlock]:
        for page in sorted(self.pages, key=lambda p: p.page_number):
            yield from page.blocks

    def blocks_by_type(self, block_type: BlockType) -> list[DocumentBlock]:
        return [b for b in self.iter_blocks() if b.type is block_type]

    def images(self) -> list[DocumentBlock]:
        return self.blocks_by_type(BlockType.image)

    def tables(self) -> list[DocumentBlock]:
        return self.blocks_by_type(BlockType.table)

    def metric_text(self) -> str:
        """Concatenated text of every entity that participates in CER/WER.

        `text` blocks always count.  `table` blocks count only for
        `text_tables` / `text_tables_images`.  `image` blocks never count -
        they are carried as file references only.
        """
        entity_set = self.entity_set
        pages: list[str] = []
        for page in sorted(self.pages, key=lambda p: p.page_number):
            chunks = [
                b.metric_text
                for b in page.blocks
                if b.metric_text
                and (
                    (b.type is BlockType.text and entity_set.text)
                    or (b.type is BlockType.table and entity_set.tables)
                )
            ]
            pages.append("\n".join(chunks))
        return "\n".join(pages)

    def content_hash(self) -> str:
        payload = self.model_dump_json(exclude={"created_at"}).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- #
#  helpers used by parsers when creating blocks
# --------------------------------------------------------------------------- #

_WS = re.compile(r"\s+")


def make_text_block(
    content: str,
    bbox: BBox4 | None = None,
    *,
    page_size: list[int] | None = None,
    source: str | None = None,
) -> DocumentBlock:
    return DocumentBlock(
        type=BlockType.text,
        content=_WS.sub(" ", content).strip(),
        bbox=bbox,
        page_size=page_size,
        source=source,
    )


def make_table_block(
    rows: list[list[Any]],
    bbox: BBox4 | None = None,
    *,
    source: str | None = None,
) -> DocumentBlock:
    clean = [
        ["" if cell is None else _WS.sub(" ", str(cell)).strip() for cell in row]
        for row in rows
    ]
    return DocumentBlock(type=BlockType.table, rows=clean, bbox=bbox, source=source)


def make_image_block(
    url: str,
    bbox: BBox4 | None = None,
    *,
    page_size: list[int] | None = None,
    caption: str | None = None,
    source: str = "crop",
) -> DocumentBlock:
    return DocumentBlock(
        type=BlockType.image,
        url=url,
        bbox=bbox,
        page_size=page_size,
        caption=caption,
        source=source,
    )


def renumber_blocks(document: DocumentJSON) -> DocumentJSON:
    """Give every block a stable, readable id: `p{page}-{index}-{type}`."""
    for page in document.pages:
        for index, block in enumerate(page.blocks):
            block.id = f"p{page.page_number}-{index + 1:03d}-{block.type.value}"
    return document
