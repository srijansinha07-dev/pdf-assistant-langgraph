"""
services/extractor.py
─────────────────────
Hybrid PDF text extraction:
  1. PyMuPDF for normal text pages (fast, lossless)
  2. Tesseract OCR fallback for image/formula-heavy pages
  3. Post-processing to fix common symbol encoding errors
"""
from __future__ import annotations
from config import OCR_THRESHOLD, OCR_DPI


import re
import fitz
import os
import subprocess

# ── Optional OCR dependencies ──────────────────────────────────────────────
try:
    from PIL import (
        Image,
        ImageFilter,
        ImageEnhance,
    )

    import pytesseract

    OCR_AVAILABLE = True

    # Windows local dev
        # Windows local dev
    if os.name == "nt":
        pytesseract.pytesseract.tesseract_cmd = (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )

    # Railway / Linux (Docker)
    else:
        pytesseract.pytesseract.tesseract_cmd = (
            "/usr/bin/tesseract"
        )

    print(
        "TESSERACT PATH:",
        pytesseract.pytesseract.tesseract_cmd
    )

except ImportError:
    OCR_AVAILABLE = False

    print(
        "OCR dependencies unavailable"
    ) 
# ── Symbol / formula regex ─────────────────────────────────────────────────
FORMULA_RE = re.compile(
    r'[μσαβρΣΩ∑√±∞≈≠≤≥∈∉]'
    r'|H[_0-9]*\s*[:=]'
    r'|[zZtTFp]\s*[=<>≤≥]'
    r'|\b(alpha|beta|sigma|mu|rho)\b'
    r'|[_^]\s*\{?[a-zA-Z0-9]+\}?'
    r'|={1,2}',
    re.IGNORECASE,
)


# ── Public API ─────────────────────────────────────────────────────────────

def extract_pdf(pdf_path: str, ocr_threshold: int = OCR_THRESHOLD) -> list[dict]:
    """
    Extract text from every page of a PDF.

    Returns list of:
      {
        page_num   : int   (1-indexed),
        text       : str,
        ocr_used   : bool,
        blocks     : list[str],    # raw text blocks from PyMuPDF
      }
    """
    doc   = fitz.open(pdf_path)
    pages = []

    for i, page in enumerate(doc):
        print(f"Processing page {i+1}")
        page_num = i + 1

        # ── PyMuPDF extraction ────────────────────────────────────────────
        raw = page.get_text(
            "text",
            flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES,
        )
        pymupdf_text = _fix_symbols(_strip_beamer_noise(raw.strip()))

        blocks = [
            b[4] for b in page.get_text("blocks") if b[6] == 0
        ]

        # ── OCR fallback decision ─────────────────────────────────────────
        # ── OCR fallback decision ─────────────────────────────────────────

        meaningful = len(re.sub(r'\s+', '', pymupdf_text))

# Detect formula/statistics pages
        formula_keywords = [
            "hypothesis",
            "proportion",
            "null",
            "alternative",
            "critical",
            "accept",
            "reject",
            "z",
            "h0",
            "h1",
            "level of significance",
            ]

        looks_like_formula_page = any(
            word in pymupdf_text.lower()
            for word in formula_keywords
            )

# Trigger OCR when:
# 1. Very little extractable text
# 2. Formula-heavy page missing equations
# 3. OCR symbols absent from extracted text
        needs_ocr = (
            meaningful < ocr_threshold
            or (
                looks_like_formula_page
                and not has_formula(pymupdf_text)
                )
            )

        ocr_text = ""
        ocr_used = False

        if needs_ocr and OCR_AVAILABLE:
            print(f"🔥 OCR TRIGGERED PAGE {page_num}")
            ocr_text = _ocr_page(page)
            print(f"📝 OCR OUTPUT PAGE {page_num}:")
            print("=" * 50)
            print(ocr_text[:1500])  # first 1500 chars
            print("=" * 50)
            ocr_used = True

        # ── Merge ─────────────────────────────────────────────────────────
        if ocr_used and ocr_text:
            if meaningful < 20:
                final_text = ocr_text
            else:
                final_text = pymupdf_text + "\n\n[OCR]\n" + ocr_text
        else:
            final_text = pymupdf_text

        pages.append({
            "page_num": page_num,
            "text":     final_text,
            "ocr_used": ocr_used,
            "blocks":   blocks,
        })

    doc.close()
    return pages


def render_page_image(pdf_path: str, page_num: int, dpi: int = 150) -> Optional[bytes]:
    """
    Render a single PDF page to PNG bytes (for the UI page preview).
    page_num is 1-indexed.
    """
    try:
        doc  = fitz.open(pdf_path)
        page = doc[page_num - 1]
        zoom = dpi / 72.0
        mat  = fitz.Matrix(zoom, zoom)
        pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        doc.close()
        return pix.tobytes("png")
    except Exception:
        return None


# ── Internal helpers ───────────────────────────────────────────────────────

def _ocr_page(page: fitz.Page) -> str:
    print(
        f" OCR RUNNING ON PAGE {page.number + 1}"
        )
    """OCR optimized for Beamer slides with formulas."""

    zoom = 5.0  # very high resolution

    mat = fitz.Matrix(zoom, zoom)

    pix = page.get_pixmap(
        matrix=mat,
        colorspace=fitz.csRGB
    )

    img = Image.frombytes(
        "RGB",
        [pix.width, pix.height],
        pix.samples
    )

    width, height = img.size

    # -----------------------------------------
    # CROP HEADER + FOOTER
    # Removes title bar and page footer noise
    # -----------------------------------------

    top_crop = int(height * 0.12)
    bottom_crop = int(height * 0.08)

    img = img.crop(
        (
            0,
            top_crop,
            width,
            height - bottom_crop
        )
    )

    # -----------------------------------------
    # PREPROCESS
    # -----------------------------------------

    img = img.convert("L")

    img = ImageEnhance.Contrast(
        img
    ).enhance(2.5)

    img = ImageEnhance.Sharpness(
        img
    ).enhance(3.0)

    # slight denoise
    img = img.filter(
        ImageFilter.MedianFilter(size=3)
    )

    # -----------------------------------------
    # DEBUG SAVE (IMPORTANT)
    # -----------------------------------------

    img.save(
        f"ocr_debug_page_{page.number+1}.png"
    )
# -----------------------------------------
# OCR CONFIG (FORMULA OPTIMIZED)
# -----------------------------------------

    configs = [
        "--oem 3 --psm 6",
        "--oem 3 --psm 11",
        "--oem 3 --psm 4",
        ]
    best_text = ""
    try:
        for cfg in configs:
            print(f"Trying OCR config: {cfg}")
            text = pytesseract.image_to_string(
                img,
                config=cfg
                )
            # Keep best OCR result
            if len(text.strip()) > len(best_text):
                best_text = text
                print(f"📝 OCR OUTPUT PAGE {page.number + 1}:")
                print("=" * 50)
                print(best_text[:2000])
                print("=" * 50)
    except Exception as e:
        print(f"OCR ERROR: {e}")
        return ""
    return _fix_ocr_math(best_text.strip())


def _fix_symbols(text: str) -> str:
    """Fix common PyMuPDF encoding failures for stats/math symbols."""
    table = {
        r'\mu':    'μ',  r'\sigma': 'σ',  r'\alpha': 'α',
        r'\beta':  'β',  r'\rho':   'ρ',  r'\bar{x}':'x̄',
        r'\hat{p}':'p̂', r'\neq':   '≠',  r'\leq':   '≤',
        r'\geq':   '≥',  r'\pm':    '±',  r'\sqrt':  '√',
        '\ufb01':  'fi', '\ufb02':  'fl',
    }
    for bad, good in table.items():
        text = text.replace(bad, good)
    return text


def _fix_ocr_math(text: str) -> str:
    """Correct common Tesseract misreads of mathematical notation."""
    fixes = [
        (r'\bHo\b',               'H0'),
        (r'\bHi\b',               'H1'),
        (r'(?<!\w)u(?=\s*[=<>])', 'μ'),
        (r'\bsigma\b',            'σ'),
        (r'\balpha\b',            'α'),
        (r'\bbeta\b',             'β'),
        (r'Za\b',                 'zα'),
        (r'z_a\b',                'zα'),
    ]
    for pattern, repl in fixes:
        text = re.sub(pattern, repl, text)
    return text


def _strip_beamer_noise(text: str) -> str:
    """Remove Beamer navigation / footer noise that pollutes chunks."""
    text = re.sub(r'^\s*\d+\s*/\s*\d+\s*$', '', text, flags=re.MULTILINE)
    # Generic: lines that are ONLY "Title  N / M" or similar navigation
    text = re.sub(r'^.*?Hypothesis Testing.*?$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    return text.strip()


def has_formula(text: str) -> bool:
    return bool(FORMULA_RE.search(text))
