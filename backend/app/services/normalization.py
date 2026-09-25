"""Text normalization used before CER/WER comparison.

Normalization is deliberately symmetric: the exact same function is applied to
the reference text and to the recognized text, so unavoidable typographic
differences (curly quotes, en-dashes, non-breaking spaces) never pollute the
error rate.
"""

from __future__ import annotations

import re
import unicodedata

from app.schemas.metrics import NormalizationOptions

# --- typography unification ------------------------------------------------- #
QUOTE_MAP = {
    # double quotes
    "\u201c": '"',  # “
    "\u201d": '"',  # ”
    "\u201e": '"',  # „
    "\u201f": '"',  # ‟
    "\u00ab": '"',  # «
    "\u00bb": '"',  # »
    "\u2033": '"',  # ″
    "\u301d": '"',
    "\u301e": '"',
    # single quotes / apostrophes
    "\u2018": "'",  # ‘
    "\u2019": "'",  # ’
    "\u201a": "'",  # ‚
    "\u201b": "'",  # ‛
    "\u2032": "'",  # ′
    "\u02bc": "'",  # ʼ
    "`": "'",
    "\u00b4": "'",  # ´
}

DASH_MAP = {
    "\u2014": "-",  # —
    "\u2013": "-",  # –
    "\u2012": "-",  # ‒
    "\u2015": "-",  # ―
    "\u2010": "-",  # ‐
    "\u2011": "-",  # ‑
    "\u2212": "-",  # − minus sign
    "\u00ad": "",   # soft hyphen
}

SPACE_MAP = {
    "\u00a0": " ",  # nbsp
    "\u2007": " ",
    "\u2009": " ",
    "\u200a": " ",
    "\u202f": " ",  # narrow nbsp
    "\u2002": " ",
    "\u2003": " ",
    "\u2004": " ",
    "\u2005": " ",
    "\u2006": " ",
    "\u200b": "",   # zero-width space
    "\ufeff": "",   # BOM
    "\t": " ",
}

# Symbol-level noise that OCR/GLM commonly differs on but that carries no meaning
LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\u00e6": "ae",
    "\u0153": "oe",
}

_WS_RE = re.compile(r"\s+")
_PUNCT_OR_SYMBOL_RE = re.compile(r"[^\w\s]|_", flags=re.UNICODE)
_WORD_RE = re.compile(r"\S+")
# soft line-break hyphenation: "ис-\nполнение" -> "исполнение".
# Only letters are joined, so numeric ranges ("5-\n10") are left untouched.
_LINE_HYPHEN_RE = re.compile(r"(?<=[^\W\d_])-\s*\n\s*(?=[^\W\d_])", flags=re.UNICODE)


def _translate(text: str, table: dict[str, str]) -> str:
    return text.translate(str.maketrans(table))


def unify_typography(text: str) -> str:
    text = _translate(text, QUOTE_MAP)
    text = _translate(text, DASH_MAP)
    text = _translate(text, SPACE_MAP)
    return _translate(text, LIGATURES)


def strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_text(text: str | None, options: NormalizationOptions | None = None) -> str:
    """Apply the configured normalization chain and return the metric string."""
    options = options or NormalizationOptions()
    if not text:
        return ""

    result = unify_typography(text)

    if options.strip_diacritics:
        result = strip_diacritics(result)
    if options.lowercase:
        result = result.casefold()
    if options.remove_punctuation:
        result = _PUNCT_OR_SYMBOL_RE.sub(" ", result)
    else:
        # join words broken across a line by a hyphen ("ис-\nполнение")
        result = _LINE_HYPHEN_RE.sub("", result)

    if options.collapse_whitespace:
        result = _WS_RE.sub(" ", result).strip()

    return result


def normalize_for_diff(
    text: str | None, options: NormalizationOptions | None = None
) -> str:
    """Like :func:`normalize_text` but keeps line structure for readable diffs."""
    options = options or NormalizationOptions()
    if not text:
        return ""
    result = unify_typography(text)
    if options.lowercase:
        result = result.casefold()
    if options.remove_punctuation:
        result = _PUNCT_OR_SYMBOL_RE.sub(" ", result)
    result = re.sub(r"[ \t]+", " ", result)
    return "\n".join(line.strip() for line in result.splitlines() if line.strip())


def tokenize(text: str) -> list[str]:
    """Whitespace word tokenizer (operates on already normalized text)."""
    return _WORD_RE.findall(text or "")
