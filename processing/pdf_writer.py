"""Writes the generated summary to a PDF (QA A3). fpdf2 needs a TrueType font that has Lithuanian letters."""
import logging
import os
import re
from datetime import date
from pathlib import Path

from fpdf import FPDF

logging.getLogger("fontTools").setLevel(logging.WARNING)     # it logs every font subsetting step at INFO

FONT_CANDIDATES = [                                      # first one that exists wins; DMS_FONT overrides
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]
_MARKDOWN = re.compile(r"\*\*|__|^#+\s*|`", re.M)


class NoFont(RuntimeError):
    """No font with Lithuanian letters was found; the message is safe to show."""


def find_fonts() -> tuple[str, str]:
    regular = os.getenv("DMS_FONT")
    if regular:
        return regular, os.getenv("DMS_FONT_BOLD", regular)
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists():
            return regular, bold if Path(bold).exists() else regular
    raise NoFont("Nerastas šriftas PDF failui (nurodykite DMS_FONT faile .env).")


def summary_pdf(title: str, body: str, sources: list[str], labels: dict, today: date | None = None) -> bytes:
    """labels: {'sources': ..., 'created': ..., 'note': ...} in the summary's language."""
    regular, bold = find_fonts()
    pdf = FPDF(format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_font("body", "", regular)
    pdf.add_font("body", "B", bold)
    pdf.set_title(title)
    pdf.add_page()
    width = pdf.epw

    pdf.set_font("body", "B", 16)
    pdf.multi_cell(width, 8, title)
    pdf.set_font("body", "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(width, 5, f"{labels['created']}: {(today or date.today()).isoformat()}")
    pdf.multi_cell(width, 5, f"{labels['sources']}: " + "; ".join(sources))
    pdf.multi_cell(width, 5, labels["note"])
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    for raw in _MARKDOWN.sub("", body).splitlines():
        line = raw.strip()
        if not line:
            pdf.ln(2)
        elif line[:2] in ("- ", "* ", "• "):
            pdf.set_font("body", "", 11)
            pdf.set_x(pdf.l_margin + 4)
            pdf.multi_cell(width - 4, 6, "• " + line[2:].strip())
        elif len(line) <= 120 and not line.endswith((".", ":", ";")):   # a document title or "Bendra santrauka"
            pdf.ln(2)
            pdf.set_font("body", "B", 12)
            pdf.multi_cell(width, 7, line)
        else:
            pdf.set_font("body", "", 11)
            pdf.multi_cell(width, 6, line)
    return bytes(pdf.output())
