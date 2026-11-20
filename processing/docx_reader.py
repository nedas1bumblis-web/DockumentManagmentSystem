from docx import Document as open_docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from processing.pdf_reader import UnreadableDocument

CHARS_PER_VIRTUAL_PAGE = 3000   # a DOCX file has no fixed pages; this approximates one A4 page of text


def _blocks(doc):
    """Paragraphs and tables in document order (doc.paragraphs alone silently skips tables)."""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc).text
        elif child.tag == qn("w:tbl"):
            for row in Table(child, doc).rows:
                cells = []
                for cell in row.cells:
                    if cell.text not in cells:      # merged cells repeat the same text
                        cells.append(cell.text)
                yield " | ".join(cells)


def read_docx(path: str) -> list[dict]:
    """Return [{'text': ..., 'page': n}] where n is a *virtual* page (about 3000 characters each)."""
    try:
        doc = open_docx(path)
        lines = [line.strip() for line in _blocks(doc)]
    except Exception as exc:
        raise UnreadableDocument("DOCX failas sugadintas arba neperskaitomas.") from exc

    pages, current, size = [], [], 0
    for line in lines:
        if not line:
            continue
        if size and size + len(line) > CHARS_PER_VIRTUAL_PAGE:
            pages.append({"text": "\n".join(current), "page": len(pages) + 1})
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        pages.append({"text": "\n".join(current), "page": len(pages) + 1})
    return pages
