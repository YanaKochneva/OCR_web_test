"""Parsing of GLM answers into schema blocks.

Kept separate from the HTTP client so the fragile part - turning a model answer
into validated blocks - is unit-testable without network access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.schemas.document import BlockType, DocumentType
from app.services.images import normalize_bbox_to_xywh

TYPE_ALIASES = {
    "text": BlockType.text,
    "paragraph": BlockType.text,
    "heading": BlockType.text,
    "title": BlockType.text,
    "line": BlockType.text,
    "caption": BlockType.text,
    "header": BlockType.text,
    "footer": BlockType.text,
    "table": BlockType.table,
    "grid": BlockType.table,
    "tabular": BlockType.table,
    "image": BlockType.image,
    "img": BlockType.image,
    "figure": BlockType.image,
    "picture": BlockType.image,
    "photo": BlockType.image,
    "diagram": BlockType.image,
    "chart": BlockType.image,
    "graphic": BlockType.image,
    "logo": BlockType.image,
    "stamp": BlockType.image,
    "seal": BlockType.image,
    "signature": BlockType.image,
    "sign": BlockType.image,
    "qr": BlockType.image,
    "barcode": BlockType.image,
}

CONTENT_KEYS = ("content", "text", "value", "body", "plain_text")
ROWS_KEYS = ("rows", "table", "data", "cells", "grid")
BBOX_KEYS = ("bbox", "box", "bounding_box", "bbox_2d", "coordinates", "coord")


@dataclass
class RawBlock:
    """A block as returned by the model, before cropping/persisting images."""

    type: BlockType
    content: str = ""
    rows: list[list[str]] = field(default_factory=list)
    bbox: list[float] | None = None


@dataclass
class ParsedAnswer:
    blocks: list[RawBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    payload_ok: bool = False


# --------------------------------------------------------------------------- #
#  JSON extraction
# --------------------------------------------------------------------------- #


def strip_code_fences(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines.pop()
        stripped = "\n".join(lines).strip()
    return stripped


def _balanced_object(text: str) -> str | None:
    """Return the first balanced {...} substring, ignoring braces in strings."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def extract_json_payload(text: str) -> Any | None:
    """Pull a JSON value out of a model answer (tolerates fences and prose)."""
    if not text:
        return None

    candidates = [strip_code_fences(text), text.strip()]
    balanced = _balanced_object(text)
    if balanced:
        candidates.append(balanced)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(_as_str(item) for item in value)
    if isinstance(value, dict):
        for key in CONTENT_KEYS:
            if key in value:
                return _as_str(value[key])
        return " ".join(_as_str(item) for item in value.values())
    return str(value)


def _as_rows(value: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    if isinstance(value, dict):
        for key in ROWS_KEYS:
            if key in value:
                return _as_rows(value[key])
        value = list(value.values())

    if not isinstance(value, list):
        return rows

    for row in value:
        if isinstance(row, list):
            rows.append([_as_str(cell).strip() for cell in row])
        elif isinstance(row, dict):
            rows.append(
                [_as_str(row.get(key, "")) for key in sorted(row.keys())]
            )
        else:
            rows.append([_as_str(row).strip()])

    if rows:
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
    return rows


def _as_bbox(value: Any) -> list[float] | None:
    if isinstance(value, dict):
        for key in BBOX_KEYS:
            if key in value:
                return _as_bbox(value[key])
        keys = ("x", "y", "w", "h")
        if all(key in value for key in keys):
            return [float(value[k]) for k in keys]
        keys = ("x0", "y0", "x1", "y1")
        if all(key in value for key in keys):
            x0, y0, x1, y1 = (float(value[k]) for k in keys)
            return [x0, y0, x1 - x0, y1 - y0]
        return None
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return None
    return None


def _pick(mapping: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _block_type(value: Any) -> BlockType | None:
    if isinstance(value, BlockType):
        return value
    if not isinstance(value, str):
        return None
    return TYPE_ALIASES.get(value.strip().lower())


def _iter_candidate_blocks(payload: Any) -> list[dict]:
    """Find the block array inside whatever envelope the model produced."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("blocks", "elements", "items", "content", "result", "page"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return _iter_candidate_blocks(value)
        # a single block returned bare
        if "type" in payload:
            return [payload]
    return []


def parse_model_answer(
    payload: Any, document_type: DocumentType, page_size: list[int]
) -> ParsedAnswer:
    """Validate and normalize the model's blocks for one page.

    Blocks whose type is not part of the selected document type are dropped
    (e.g. a diagram returned for `text_only`) together with a warning, so the
    metrics never depend on entities the benchmark excludes by definition.
    """
    entity_set = document_type.entity_set
    answer = ParsedAnswer()
    raw_blocks = _iter_candidate_blocks(payload)

    if not raw_blocks:
        answer.warnings.append("GLM не вернул ни одного блока для страницы.")
        return answer

    answer.payload_ok = True
    for index, raw in enumerate(raw_blocks):
        block_type = _block_type(_pick(raw, ("type", "block_type", "kind", "label")))
        if block_type is None:
            answer.warnings.append(f"Блок #{index + 1}: неизвестный тип, пропущен.")
            continue

        if block_type is BlockType.table and not entity_set.tables:
            answer.warnings.append(
                "Табличный блок проигнорирован: тип документа не учитывает таблицы."
            )
            continue
        if block_type is BlockType.image and not entity_set.images:
            answer.warnings.append(
                "Блок-изображение проигнорирован: тип документа не учитывает изображения."
            )
            continue

        if block_type is BlockType.text:
            content = _as_str(_pick(raw, CONTENT_KEYS)).strip()
            if not content:
                continue
            answer.blocks.append(
                RawBlock(
                    type=BlockType.text,
                    content=content,
                    bbox=normalize_bbox_to_xywh(
                        _as_bbox(_pick(raw, BBOX_KEYS)) or [], page_size
                    ),
                )
            )
            continue

        if block_type is BlockType.table:
            rows = _as_rows(_pick(raw, ROWS_KEYS))
            if not rows:
                answer.warnings.append(f"Блок #{index + 1}: пустая таблица, пропущена.")
                continue
            answer.blocks.append(
                RawBlock(
                    type=BlockType.table,
                    rows=rows,
                    bbox=normalize_bbox_to_xywh(
                        _as_bbox(_pick(raw, BBOX_KEYS)) or [], page_size
                    ),
                )
            )
            continue

        # image: geometry only, the picture itself is cropped by the backend
        bbox = normalize_bbox_to_xywh(_as_bbox(_pick(raw, BBOX_KEYS)) or [], page_size)
        if not bbox or bbox[2] <= 0 or bbox[3] <= 0:
            answer.warnings.append(
                f"Блок #{index + 1}: изображение без корректного bbox, пропущено."
            )
            continue
        answer.blocks.append(RawBlock(type=BlockType.image, bbox=bbox))

    if not answer.blocks:
        answer.warnings.append("После фильтрации не осталось ни одного блока.")
    return answer
