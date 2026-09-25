"""Prompt construction for the GLM 4.6 (multimodal) recognition call.

One request == one page image.  The model is asked to return a strict JSON
object with a `blocks` array that maps 1:1 onto the shared document schema.

Critical rule (from the brief): the model must **locate** figures/diagrams but
must never transcribe or describe them.  It returns a bounding box, the backend
crops that box out of the page bitmap and stores the picture as-is.
"""

from __future__ import annotations

from app.schemas.document import DocumentType

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = (
    "You are a precise document-layout and OCR engine. "
    "You convert a raster image of one document page into structured JSON. "
    "You never add commentary, never summarise and never invent content that "
    "is not visible on the page. Answer with a single JSON object and nothing "
    "else - no markdown fences, no explanations."
)

_COMMON_RULES = """\
GLOBAL RULES
1. Read the page image top to bottom and emit one object per logical block.
2. `bbox` is always [x, y, w, h] in PIXELS of the provided image, measured from
   the top-left corner. Give the tightest box that still contains the whole
   block, including any handwriting that belongs to it.
3. Reproduce the original language, spelling, digits and punctuation exactly.
   Never translate, never correct the author's spelling.
4. Handwritten additions (signatures, dates, margin notes) must be transcribed
   as text in the block they belong to.
5. Return `{"blocks": [...]}` with blocks in reading order.
6. Do not emit empty blocks and do not merge two different blocks into one.
"""

_TEXT_RULES = """\
TEXT BLOCKS
- {"type": "text", "content": "<verbatim text>", "bbox": [x, y, w, h]}
- One block per paragraph, heading, list item, header, footer or caption.
- Join the lines of a single paragraph with a space; keep the paragraph as one
  block even if it spans several visual lines.
- Preserve the reading order of multi-column layouts.
"""

_TABLE_RULES = """\
TABLE BLOCKS
- {"type": "table", "rows": [["cell", "cell"], ["cell", "cell"]], "bbox": [x, y, w, h]}
- One block per table. `rows` is a rectangular array of strings, row 0 first.
- Header rows stay in `rows` as the first row(s) - do not extract them
  separately and do not repeat them.
- Every row must have the same number of cells. Use "" for an empty cell so the
  grid stays rectangular.
- Numbers keep their original formatting (spaces, commas, currency signs).
- Do not emit text blocks for the text that already sits inside a table.
"""

_IMAGE_RULES = """\
IMAGE BLOCKS
- {"type": "image", "bbox": [x, y, w, h]}
- Emit this for every figure, diagram, chart, screenshot, photograph, logo,
  stamp, seal, QR/barcode or other non-text graphics.
- NEVER describe, transcribe or interpret the picture. Do not output captions
  inside the image block; captions that are printed text are separate text
  blocks.
- Cover the whole graphic with a single bbox. Do not emit an image block for
  page background, ruled lines or table borders.
"""

_RESPONSE_SHAPE = """\
RESPONSE SHAPE (strict)
{"blocks": [ ... ]}
"""


def _rules_for(document_type: DocumentType) -> str:
    entity_set = document_type.entity_set
    parts = [_COMMON_RULES, _TEXT_RULES]
    if entity_set.tables:
        parts.append(_TABLE_RULES)
    if entity_set.images:
        parts.append(_IMAGE_RULES)
    return "\n".join(parts)


def build_system_prompt(document_type: DocumentType) -> str:
    return SYSTEM_PROMPT


def build_page_prompt(
    document_type: DocumentType, page_number: int, page_size: list[int]
) -> str:
    """User turn: rules + the geometry the model must answer in."""
    allowed = ["text"]
    if document_type.entity_set.tables:
        allowed.append("table")
    if document_type.entity_set.images:
        allowed.append("image")

    return (
        f"{_rules_for(document_type)}\n"
        f"PAGE CONTEXT\n"
        f"- document_type: {document_type.value}\n"
        f"- page_number: {page_number} (1-based)\n"
        f"- image size: {page_size[0]} x {page_size[1]} pixels\n"
        f"- allowed block types on this page: {', '.join(allowed)}\n"
        f"\n{_RESPONSE_SHAPE}"
    )


def build_repair_prompt(raw_answer: str) -> str:
    """Second chance when the first answer was not valid JSON."""
    excerpt = raw_answer.strip()[:4000]
    return (
        "Your previous answer was not valid JSON. "
        "Convert it into exactly one JSON object with a `blocks` array, using "
        "only the allowed block types, and output nothing else.\n\n"
        f"PREVIOUS ANSWER:\n{excerpt}"
    )


EXTRACTION_JSON_SCHEMA = {
    "name": "page_extraction",
    "schema": {
        "type": "object",
        "properties": {
            "blocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["text", "table", "image"]},
                        "content": {"type": "string"},
                        "rows": {
                            "type": "array",
                            "items": {"type": "array", "items": {"type": "string"}},
                        },
                        "bbox": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 4,
                            "maxItems": 4,
                        },
                    },
                    "required": ["type"],
                },
            }
        },
        "required": ["blocks"],
    },
}
