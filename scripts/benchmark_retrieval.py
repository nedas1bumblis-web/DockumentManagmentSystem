"""P4 (plan, section 5): how fast is search_chunks when one user has 1000 documents of ~85 chunks?

    python -m scripts.benchmark_retrieval [chunks_per_document]

Fills a throw-away user with random vectors (generated inside Postgres), times searches over all documents,
then deletes everything again. Takes a few minutes and ~0.6 GB of temporary disk space in the container.
"""
import random
import statistics
import sys
import time
import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app_config import EMBEDDING_DIM, MAX_DOCUMENTS_PER_USER, TOP_K
from database.engine import get_engine
from database.models import Category, Department, Document, User
from rag.mock_ai import normalize
from rag.retrieval import search_chunks
from security import hash_password

LIMIT_SECONDS = 30                                     # NFR-02 covers the whole answer, retrieval is one part


def main() -> None:
    per_document = int(sys.argv[1]) if len(sys.argv) > 1 else 85
    engine = get_engine()
    with Session(engine) as session:
        department_id = session.scalar(select(Department.department_id).limit(1))
        category_id = session.scalar(select(Category.category_id).limit(1))
        user = User(email=f"bench-{uuid.uuid4().hex[:8]}@test.lt", password_hash=hash_password("Bench1234!"),
                    first_name="Bench", last_name="Mark", department_id=department_id)
        session.add(user)
        session.commit()
        user_id = user.user_id
        try:
            started = time.perf_counter()
            documents = [Document(author_id=user_id, department_id=department_id, category_id=category_id,
                                  title=f"bench {n}", file_type="pdf", file_path="none", status="ready")
                         for n in range(MAX_DOCUMENTS_PER_USER)]
            session.add_all(documents)
            session.commit()
            ids = [d.document_id for d in documents]
            session.execute(text(f"""
                INSERT INTO chunks (document_id, chunk_index, page, content, embedding)
                SELECT d.document_id, c.i, 1 + c.i / 3, 'benchmark chunk',
                       (SELECT array_agg(random() - 0.5)::vector({EMBEDDING_DIM})
                          FROM generate_series(1, {EMBEDDING_DIM}) WHERE c.i >= 0 AND d.document_id > 0)
                  FROM documents d CROSS JOIN generate_series(0, :per_document - 1) AS c(i)
                 WHERE d.author_id = :user_id"""), {"per_document": per_document, "user_id": user_id})
            session.commit()
            session.execute(text("ANALYZE chunks"))
            total = len(ids) * per_document
            print(f"inserted {len(ids)} documents x {per_document} chunks = {total} vectors "
                  f"({EMBEDDING_DIM} dims) in {time.perf_counter() - started:.0f} s")

            timings = {"all 1000 documents": ids, "10 documents": ids[:10], "1 document": ids[:1]}
            for label, selection in timings.items():
                runs = []
                for _ in range(5):
                    query = normalize([random.random() - 0.5 for _ in range(EMBEDDING_DIM)])
                    t0 = time.perf_counter()
                    hits = search_chunks(session, query, user_id, selection, k=TOP_K)
                    runs.append(time.perf_counter() - t0)
                    session.commit()
                assert len(hits) == TOP_K
                print(f"search over {label:20}: median {statistics.median(runs) * 1000:7.0f} ms, "
                      f"worst {max(runs) * 1000:7.0f} ms")
            size = session.execute(text("select pg_size_pretty(pg_total_relation_size('chunks'))")).scalar()
            print(f"chunks table size: {size}")
        finally:
            session.rollback()
            session.execute(delete(User).where(User.user_id == user_id))      # cascades to documents and chunks
            session.commit()
            print("benchmark data removed")


if __name__ == "__main__":
    main()
