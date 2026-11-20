from sqlalchemy import select
from sqlalchemy.orm import Session

from app_config import TOP_K
from database.models import Chunk, Document


def search_chunks(session: Session, query_vector: list[float], user_id: int, document_ids: list[int],
                  k: int = TOP_K) -> list[dict]:
    """The k chunks nearest to the question, searched ONLY in ready documents that belong to user_id.

    The ownership filter lives here, in SQL, so no caller can forget it (QA risk 2 / TS-04).
    """
    if not document_ids:
        return []
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    statement = (
        select(Chunk.chunk_id, Chunk.page, Chunk.content, Document.document_id, Document.title, distance)
        .join(Document, Document.document_id == Chunk.document_id)
        .where(Document.author_id == user_id,
               Document.document_id.in_(document_ids),
               Document.status == "ready")
        .order_by(distance)
        .limit(k)
    )
    return [
        {"chunk_id": row.chunk_id, "document_id": row.document_id, "document": row.title,
         "page": row.page, "text": row.content, "similarity": 1.0 - float(row.distance)}
        for row in session.execute(statement)
    ]
