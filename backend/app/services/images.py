"""Crop regions of rendered pages and persist them as static PNG files.

Design rule from the brief: figures, diagrams, stamps and signatures are **never
transcribed**.  They are cropped out of the page bitmap exactly as they appear
and referenced by URL from the JSON, e.g.

    /static/images/<session_id>/<sha1>.png
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image

# Mounted by `app.main` -> StaticFiles(directory=settings.data_path)
STATIC_PREFIX = "/static"
IMAGES_SUBDIR = "images"

MIN_CROP_PIXELS = 24  # ignore dust specks / hairlines


class ImageStore:
    """Content-addressed store for page crops."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.root = self.data_dir / IMAGES_SUBDIR
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths ------------------------------------------------------------- #
    def session_dir(self, session_id: str) -> Path:
        path = self.root / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def url_for(session_id: str, filename: str) -> str:
        return f"{STATIC_PREFIX}/{IMAGES_SUBDIR}/{session_id}/{filename}"

    @staticmethod
    def resolve_url(url: str, data_dir: Path) -> Path | None:
        """`/static/images/s/abc.png` -> `<data_dir>/images/s/abc.png`."""
        if not url.startswith(f"{STATIC_PREFIX}/"):
            return None
        relative = url[len(STATIC_PREFIX) + 1 :].replace("/", "/")
        candidate = (Path(data_dir) / relative).resolve()
        try:
            candidate.relative_to(Path(data_dir).resolve())
        except ValueError:
            return None  # path traversal attempt
        return candidate

    # -- saving ------------------------------------------------------------ #
    def save_bytes(
        self,
        session_id: str,
        blob: bytes,
        *,
        extension: str = ".png",
        tag: str = "img",
    ) -> str:
        """Write `blob` (idempotently, keyed by content hash) and return its URL."""
        digest = hashlib.sha1(blob).hexdigest()[:16]
        filename = f"{tag}-{digest}{extension}"
        target = self.session_dir(session_id) / filename
        if not target.exists():
            target.write_bytes(blob)
        return self.url_for(session_id, filename)

    def save_image(
        self, session_id: str, image: Image.Image, *, tag: str = "img"
    ) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return self.save_bytes(session_id, buffer.getvalue(), tag=tag)

    def crop(
        self,
        session_id: str,
        page_image: Image.Image,
        bbox: list[float],
        *,
        tag: str = "crop",
        padding: int = 4,
    ) -> str | None:
        """Crop `bbox` = [x, y, w, h] out of `page_image` and persist it.

        Returns ``None`` when the box is degenerate or out of bounds, so the
        caller can drop the corresponding block instead of storing junk.
        """
        region = crop_region(page_image, bbox, padding=padding)
        if region is None:
            return None
        return self.save_image(session_id, region, tag=tag)


def crop_region(
    page_image: Image.Image, bbox: list[float], *, padding: int = 4
) -> Image.Image | None:
    """Clamp `bbox` ([x, y, w, h]) to the page and return the cropped image."""
    if not bbox or len(bbox) != 4:
        return None

    x, y, width, height = (float(value) for value in bbox)
    if width <= 0 or height <= 0:
        # tolerate bbox given as [x0, y0, x1, y1]
        width, height = x, y
        x, y = 0.0, 0.0
    if width <= 0 or height <= 0:
        return None

    left = max(0, int(round(x)) - padding)
    top = max(0, int(round(y)) - padding)
    right = min(page_image.width, int(round(x + width)) + padding)
    bottom = min(page_image.height, int(round(y + height)) + padding)

    if right - left < MIN_CROP_PIXELS or bottom - top < MIN_CROP_PIXELS:
        return None

    return page_image.crop((left, top, right, bottom)).convert("RGB")


def normalize_bbox_to_xywh(
    bbox: list[float], page_size: list[int] | None
) -> list[float] | None:
    """Accept ``[x0, y0, x1, y1]`` or ``[x, y, w, h]`` and return ``[x, y, w, h]``.

    GLM is asked for ``[x, y, w, h]`` but different checkpoints occasionally
    answer with corner coordinates, so the two encodings are disambiguated
    using the page size when it is known.
    """
    if not bbox or len(bbox) != 4:
        return None
    try:
        values = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None

    x, y, third, fourth = values

    if page_size and len(page_size) == 2:
        page_w, page_h = float(page_size[0]), float(page_size[1])
        looks_like_corners = third > x and fourth > y and (
            third <= page_w * 1.05 and fourth <= page_h * 1.05
        )
        looks_like_size = x + third <= page_w * 1.05 and y + fourth <= page_h * 1.05
        if looks_like_corners and not looks_like_size:
            return [round(x, 2), round(y, 2), round(third - x, 2), round(fourth - y, 2)]

    return [round(v, 2) for v in values]


def clamp_bbox(bbox: list[float], page_size: list[int]) -> list[float]:
    """Keep a bbox inside the page rectangle."""
    x, y, width, height = bbox
    page_w, page_h = float(page_size[0]), float(page_size[1])
    x = min(max(x, 0.0), page_w)
    y = min(max(y, 0.0), page_h)
    width = max(0.0, min(width, page_w - x))
    height = max(0.0, min(height, page_h - y))
    return [round(x, 2), round(y, 2), round(width, 2), round(height, 2)]
