import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect


class UnreadableDocument(Exception):
    """The file cannot be turned into text (encrypted, corrupt, ...). The message is safe to show to the user."""


def read_pdf(path: str) -> list[dict]:
    """Return [{'text': ..., 'page': 1-based page number}] for every page that has text."""
    pages = []
    try:
        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    pages.append({"text": text, "page": page_number})
                page.flush_cache()                       # keeps memory flat on long PDFs
    except Exception as exc:                             # pdfminer raises many different errors for broken files
        original = exc.args[0] if exc.args else exc      # pdfplumber wraps the real error in PdfminerException
        if isinstance(original, PDFPasswordIncorrect):
            raise UnreadableDocument("PDF failas apsaugotas slaptažodžiu.") from exc
        raise UnreadableDocument("PDF failas sugadintas arba neperskaitomas.") from exc
    return pages
