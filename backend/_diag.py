"""Temporary diagnostics for the test failures (deleted after use)."""

import pathlib
import unicodedata

from app.schemas.metrics import NormalizationOptions
from app.services.normalization import normalize_text, unify_typography

print("1. nbsp/zwsp:", repr(normalize_text("Итого\u00a0сумма\u200b:\u202f100")))
print("2. hyphen break:", repr(normalize_text("ис-\nполнение")))
print("3. ligature:", repr(unify_typography("o\ufb01ce")))
print("   ligature kinds:", [hex(ord(c)) for c in "o\ufb01ce"])
print("   names:", [unicodedata.name(c) for c in "o\ufb01ce"])
print("4. punct:", repr(normalize_text("Цена: 1 200,50 руб.", NormalizationOptions(remove_punctuation=True))))

candidates = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
found = [p for p in candidates if pathlib.Path(p).exists()]
print("5. cyrillic fonts available:", found)

if found:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Договор поставки № 42",
        fontsize=12,
        fontname="cyr",
        fontfile=found[0],
    )
    tmp = pathlib.Path("_diag_cyr.pdf")
    doc.save(str(tmp))
    doc.close()
    doc = pymupdf.open(str(tmp))
    text = doc.load_page(0).get_text("text")
    print("6. roundtrip:", repr(text.strip()))
    print("   equal:", text.strip() == "Договор поставки № 42")
    doc.close()
    tmp.unlink(missing_ok=True)
