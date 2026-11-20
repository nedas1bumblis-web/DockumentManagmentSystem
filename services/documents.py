import logging
from datetime import date
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app_config import MAX_DOCUMENTS_PER_USER
from database.models import Answer, Category, Document, Source, User, UserQuery
from services.ingest import ingest_document
from services.storage import UploadRejected, default_title, save_upload

log = logging.getLogger(__name__)


def upload_document(session: Session, user: User, filename: str, data: bytes, title: str | None = None,
                    category_id: int | None = None, kind: str = "document",
                    document_date: date | None = None) -> Document:
    """KD 5.1 + 5.2: store the file and tag it with metadata (category, department, date, author)."""
    owned = session.scalar(select(func.count()).select_from(Document).where(Document.author_id == user.user_id))
    if owned >= MAX_DOCUMENTS_PER_USER:                                        # QA A3: up to 1000 documents
        raise UploadRejected(f"Galima saugoti ne daugiau kaip {MAX_DOCUMENTS_PER_USER} dokumentų.")
    category_id = _category_or_default(session, category_id)
    user_id, department_id = user.user_id, user.department_id                  # read before commits expire `user`
    path, file_type = save_upload(filename, data)
    return ingest_document(session, author_id=user_id, department_id=department_id, category_id=category_id,
                           title=(title or default_title(filename)), file_path=path, file_type=file_type, kind=kind,
                           document_date=document_date)


def _category_or_default(session: Session, category_id: int | None) -> int:
    if category_id is not None:
        if session.get(Category, category_id) is None:
            raise UploadRejected("Tokios kategorijos nėra.")
        return category_id
    return session.scalar(select(Category.category_id).order_by(Category.category_id).limit(1))


def parse_document_date(value: str | None) -> date | None:
    """Date typed in the form (YYYY-MM-DD); empty means "today" (the database default)."""
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise UploadRejected("Neteisinga dokumento data.") from None
    if not date(1900, 1, 1) <= parsed <= date.today():
        raise UploadRejected("Dokumento data negali būti ateityje.")
    return parsed


def rename_document(session: Session, user: User, document_id: int, new_title: str) -> None:
    update_document(session, user, document_id, title=new_title)


def update_document(session: Session, user: User, document_id: int, *, title: str | None = None,
                    category_id: int | None = None, document_date: date | None = None) -> None:
    """Change the title and the metadata (KD 5.2) of one of my documents; None leaves a field as it is."""
    document = _owned_document(session, user, document_id)
    if title is not None:
        document.title = title.strip()[:200] or document.title
    if category_id is not None:
        document.category_id = _category_or_default(session, category_id)
    if document_date is not None:
        document.document_date = document_date
    session.commit()


def delete_document(session: Session, user: User, document_id: int) -> None:
    """Erase a document completely: file, chunks, and every stored question/answer that quoted it."""
    document = _owned_document(session, user, document_id)
    file_path = document.file_path
    cited_answers = select(Source.answer_id).where(Source.document_id == document_id)
    cited_queries = select(Answer.query_id).where(Answer.answer_id.in_(cited_answers))
    session.execute(delete(UserQuery).where(UserQuery.query_id.in_(cited_queries)))   # DB cascades to answers, sources
    session.delete(document)                                                          # DB cascades to chunks
    session.commit()
    try:
        Path(file_path).unlink(missing_ok=True)
    except OSError:
        log.exception("Could not remove file %s after deleting document %s", file_path, document_id)


def _owned_document(session: Session, user: User, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if document is None or document.author_id != user.user_id:     # same answer for "missing" and "not yours"
        raise LookupError("Document not found")
    return document
