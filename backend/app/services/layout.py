"""Deterministic reading-order sorting.

Both documents are sorted with the *same* function before comparison, otherwise
CER/WER would measure block ordering differences instead of recognition quality.

The heuristic groups blocks into visual lines (blocks whose top edges are within
a tolerance band of each other) and orders each band left-to-right.  For
single-column documents this is exact; for multi-column layouts it is an
approximation, which is documented in the README.
"""

from __future__ import annotations

from statistics import median

from app.schemas.document import DocumentBlock, DocumentJSON, DocumentPage

MIN_TOLERANCE = 6.0
TOLERANCE_PAGE_RATIO = 0.008
TOLERANCE_HEIGHT_RATIO = 0.45


def _tolerance(page: DocumentPage, blocks: list[DocumentBlock]) -> float:
    heights = [b.bbox[3] for b in blocks if b.bbox and b.bbox[3] > 0]
    base = median(heights) * TOLERANCE_HEIGHT_RATIO if heights else 0.0
    page_based = (page.height or 0) * TOLERANCE_PAGE_RATIO
    return max(MIN_TOLERANCE, base, page_based)


def sort_page_blocks(page: DocumentPage) -> DocumentPage:
    """Reorder `page.blocks` into reading order (bbox-less blocks keep order)."""
    blocks = page.blocks
    positioned = [block for block in blocks if block.bbox]
    unpositioned = [block for block in blocks if not block.bbox]

    if len(positioned) < 2:
        return page

    tolerance = _tolerance(page, positioned)
    ordered = sorted(positioned, key=lambda b: (b.bbox[1], b.bbox[0]))

    bands: list[dict] = []
    for block in ordered:
        top = block.bbox[1]
        for band in bands:
            if abs(band["top"] - top) <= tolerance:
                band["items"].append(block)
                band["top"] = min(band["top"], top)
                break
        else:
            bands.append({"top": top, "items": [block]})

    bands.sort(key=lambda band: band["top"])
    result: list[DocumentBlock] = []
    for band in bands:
        band["items"].sort(key=lambda b: b.bbox[0])
        result.extend(band["items"])
    result.extend(unpositioned)

    page.blocks = result
    return page


def sort_document_reading_order(document: DocumentJSON) -> DocumentJSON:
    for page in document.pages:
        sort_page_blocks(page)
    return document
