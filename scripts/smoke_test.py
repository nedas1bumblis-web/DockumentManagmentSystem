"""End-to-end check against YOUR Postgres (Docker) with the AI switched to the offline mock.

First time (or after the models changed):  python -m init_db --reset
Then:                                      python -m scripts.smoke_test
It creates two throw-away users and removes them again. Nothing is sent to Gemini.
"""
import io
import os
import sys
from pathlib import Path

os.environ["USE_MOCK_AI"] = "1"            # must be set before app_config is imported

from docx import Document as new_docx                   # noqa: E402
from sqlalchemy import delete, func, select              # noqa: E402
from sqlalchemy.orm import Session                       # noqa: E402

from database.engine import get_engine                   # noqa: E402
from database.models import Chunk, Department, Document, User   # noqa: E402
from security import LOCK_MINUTES                        # noqa: E402
from services.auth import login, register_user           # noqa: E402
from services.documents import delete_document, upload_document   # noqa: E402
from services.qa import ask_question                     # noqa: E402

SAMPLE = Path("samples/metodiniai.pdf")
failures = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    doc = new_docx()
    doc.add_paragraph(text)
    doc.save(buffer)
    return buffer.getvalue()


def main() -> None:
    engine = get_engine()
    with Session(engine) as session:
        department_id = session.scalar(select(Department.department_id).limit(1))
        check("seed department exists (run init_db first)", department_id is not None)
        v1 = register_user(session, email="smoke1@test.lt", password="Test1234!", first_name="V", last_name="Vienas", department_id=department_id)
        v2 = register_user(session, email="smoke2@test.lt", password="Test1234!", first_name="V", last_name="Du", department_id=department_id)
        v1_id, v2_id = v1.user_id, v2.user_id
        try:
            hashed = session.scalar(select(User.password_hash).where(User.user_id == v1_id))
            check("password stored as bcrypt (TS-05 step 1)", hashed.startswith("$2b$") and len(hashed) == 60, hashed[:7])

            d1 = upload_document(session, v1, SAMPLE.name, SAMPLE.read_bytes())
            d2 = upload_document(session, v2, "travel_policy.docx",
                                 docx_bytes("Employees may claim travel expenses up to 100 EUR per day."))
            d1_id, d2_id = d1.document_id, d2.document_id
            check("PDF ingested", d1.status == "ready", f"{d1.status} {d1.error_message}")
            check("DOCX ingested", d2.status == "ready", f"{d2.status} {d2.error_message}")
            chunks = session.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == d1_id))
            check("chunks were stored", chunks > 10, str(chunks))

            result = ask_question(session, v1, "Kokios paraštės paliekamos darbo lape?", [d1_id])
            check("answer has a source with a page", bool(result["sources"]) and result["sources"][0]["page"] is not None)

            stolen = ask_question(session, v1, "What are the travel expenses per day?", [d2_id])   # V2's document!
            check("V1 cannot search V2's document (TS-04)", stolen["sources"] == [] and "100 EUR" not in stolen["answer"], stolen["answer"][:60])

            for attempt in range(1, 5):
                status, _ = login(session, "smoke1@test.lt", "Klaida111")
                check(f"wrong password #{attempt} is not locked", status == "bad_credentials", status)
            status, _ = login(session, "smoke1@test.lt", "Klaida111")
            check("5th wrong password locks the account", status == "locked", status)
            status, _ = login(session, "smoke1@test.lt", "Test1234!")
            check(f"right password is refused during the {LOCK_MINUTES}-minute lock", status == "locked", status)
            status, _ = login(session, "smoke2@test.lt", "Test1234!")
            check("another user can still log in", status == "ok", status)

            file_path = Path(session.scalar(select(Document.file_path).where(Document.document_id == d1_id)))
            delete_document(session, v1, d1_id)
            check("delete removes document and chunks", session.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == d1_id)) == 0)
            check("delete removes the file from disk", not file_path.exists())
            try:
                delete_document(session, v1, d2_id)               # not V1's document
                check("V1 cannot delete V2's document", False)
            except LookupError:
                check("V1 cannot delete V2's document", True)
        finally:
            session.rollback()
            leftovers = session.scalars(select(Document.file_path).where(Document.author_id.in_([v1_id, v2_id]))).all()
            session.execute(delete(User).where(User.user_id.in_([v1_id, v2_id])))   # cascades to documents and chunks
            session.commit()
            for path in leftovers:
                Path(path).unlink(missing_ok=True)
    print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
