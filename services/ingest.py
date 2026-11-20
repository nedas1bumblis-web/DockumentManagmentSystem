import logging
from datetime import date

from sqlalchemy.orm import Session

from app_config import CHUNK_OVERLAP, CHUNK_SIZE
from database.models import Chunk, Document
from processing.chunker import chunk_pages
from processing.docx_reader import read_docx
from processing.pdf_reader import UnreadableDocument, read_pdf
from processing.text_cleaner import clean_text, strip_repeated_lines
from rag.embedder import embed_texts

log = logging.getLogger(__name__)


def ingest_document(session: Session, *, author_id: int, department_id: int, category_id: int, title: str,
                    file_path: str, file_type: str, kind: str = "document",
                    document_date: date | None = None) -> Document:
    """Read -> clean -> chunk -> embed -> store. The document ends as 'ready' or 'failed', never half-done."""
    document = Document(author_id=author_id, department_id=department_id, category_id=category_id, title=title,
                        file_path=file_path, file_type=file_type, kind=kind, status="processing")
    if document_date is not None:
        document.document_date = document_date                # otherwise the database fills in today
    session.add(document)
    session.commit()
    document_id = document.document_id                       # read it now: commit() expires the object
    try:
        pages = read_pdf(file_path) if file_type == "pdf" else read_docx(file_path)
        pages = [{**p, "text": clean_text(p["text"])} for p in strip_repeated_lines(pages)]
        chunks = chunk_pages(pages, CHUNK_SIZE, CHUNK_OVERLAP)
        if not chunks:
            raise UnreadableDocument("Faile nerasta teksto (nuskenuotam dokumentui reikia teksto atpažinimo).")
        vectors = embed_texts([c["text"] for c in chunks], "RETRIEVAL_DOCUMENT")
        session.add_all(
            Chunk(document_id=document_id, chunk_index=c["index"], page=c["page"], content=c["text"], embedding=v)
            for c, v in zip(chunks, vectors)
        )
        document = session.get(Document, document_id)
        document.page_count = max(p["page"] for p in pages)
        document.status = "ready"
        session.commit()
    except Exception as exc:
        session.rollback()                                    # throws away every chunk of this attempt
        document = session.get(Document, document_id)
        document.status = "failed"
        document.error_message = str(exc) if isinstance(exc, UnreadableDocument) else "Apdoroti nepavyko, bandykite vėliau."
        session.commit()
        if not isinstance(exc, UnreadableDocument):
            log.exception("Ingest of document %s failed", document_id)
    return document
