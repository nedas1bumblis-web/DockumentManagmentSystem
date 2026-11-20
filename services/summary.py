"""QA A3: the system creates a PDF that summarises the documents the user selected.

The PDF is stored like an uploaded summary (kind = 'summary', FR-05): it is listed under "Apibendrinimai",
can be downloaded, and its text is searchable like any other document.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Chunk, Document, User
from processing.pdf_writer import summary_pdf
from rag.llm import generate_summary
from services.documents import upload_document
from services.storage import UploadRejected

MAX_SUMMARY_DOCUMENTS = 10
MAX_SUMMARY_CHARS = 120_000        # text sent to the AI in total; long documents are cut to their share
LABELS = {
    "lt": {"title": "Apibendrinimas", "created": "Sukurta", "sources": "Dokumentai",
           "note": "Apibendrinimą parengė dirbtinis intelektas pagal pasirinktus dokumentus; prieš remdamiesi "
                   "patikrinkite originalus."},
    "en": {"title": "Summary", "created": "Created", "sources": "Documents",
           "note": "This summary was written by AI from the selected documents; check the originals before "
                   "relying on it."},
}


def create_summary(session: Session, user: User, document_ids: list[int], language: str = "lt",
                   title: str | None = None) -> Document:
    if language not in LABELS:
        language = "lt"
    document_ids = list(dict.fromkeys(document_ids))
    if not document_ids:
        raise UploadRejected("Pasirinkite bent vieną dokumentą.")
    if len(document_ids) > MAX_SUMMARY_DOCUMENTS:
        raise UploadRejected(f"Apibendrinti galima ne daugiau kaip {MAX_SUMMARY_DOCUMENTS} dokumentų vienu metu.")
    documents = session.scalars(select(Document).where(Document.author_id == user.user_id,     # only my own
                                                       Document.document_id.in_(document_ids),
                                                       Document.status == "ready")
                                .order_by(Document.title)).all()
    if len(documents) != len(document_ids):
        raise UploadRejected("Pasirinkite bent vieną dokumentą.")

    share = MAX_SUMMARY_CHARS // len(documents)
    texts = []
    for document in documents:
        chunks = session.scalars(select(Chunk.content).where(Chunk.document_id == document.document_id)
                                 .order_by(Chunk.chunk_index)).all()
        texts.append({"title": document.title, "text": "\n".join(chunks)[:share]})
    session.commit()                                   # release the connection while the AI works

    body = generate_summary(texts, language)
    labels = LABELS[language]
    title = (title or "").strip()[:200] or f"{labels['title']} {datetime.now():%Y-%m-%d %H.%M}"
    data = summary_pdf(title, body, [d["title"] for d in texts], labels)
    return upload_document(session, user, f"{title}.pdf", data, title=title, kind="summary")
