"""Gold set (plan, section 5, A1) and TS-06 part A: 10 questions with known answers, against the REAL Gemini.

    python -m scripts.gold_set            # real Gemini (uses your quota; sends samples/metodiniai.pdf to Google)
    $env:USE_MOCK_AI="1"; python -m scripts.gold_set   # wiring only
    python -m scripts.gold_set --f4       # TS-06 A / FR-02: the 10 F4 files, all 10 selected, one question each

Rerun after every prompt or model change. Uses a throw-away user and removes it again.
Only the public sample document is used (decision D5: no private documents on the free tier).
--f4 uses samples/test_files/dok01.pdf … dok10.pdf (make them with `python -m scripts.make_test_files`); an answer
passes when it has the expected words, cites the right file and page, and comes within 30 s. FR-02 needs >= 9/10.
"""
import sys
import time
import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app_config import EMBEDDING_MODEL, GEMINI_MODEL, USE_MOCK_AI
from database.engine import get_engine
from database.models import Department, Document, User
from services.auth import register_user
from services.documents import upload_document
from services.qa import ask_question

SAMPLE = Path("samples/metodiniai.pdf")
LITHUANIAN_LETTERS = set("ąčęėįšųūž")
ENGLISH_WORDS = (" the ", " is ", " are ", " should ", " recommended ", " pages")
LIMIT_SECONDS = 30                                    # NFR-02

# (question, words that must appear in the answer (any one of them), page the source should be on or None)
GOLD = [
    ("Kokia referato apimtis?", ["5–10", "5-10", "5 – 10", "nuo 5 iki 10"], 5),
    ("Kokio senumo literatūra rekomenduojama naudotis rašto darbe?", ["5 met", "penkerių"], 19),
    ("Kokia dalis literatūros šaltinių turėtų būti užsienio autorių?", ["trečdal", "1/3"], 19),
    ("Kokią dalį viso rašto darbo turi sudaryti praktinė dalis?", ["trečdal", "1/3"], 21),
    ("Kokiu šriftu formatuojamos trečio lygio antraštės?", ["Times New Roman"], 9),
    ("Koks rekomenduojamas antraštės šrifto dydis skaidrėse?", ["32"], 23),
    ("Kokios paraštės paliekamos darbo lape?", ["1 cm", "3 cm", "2 cm"], None),
    ("What font size is recommended for slide titles?", ["32"], 23),                       # TS-03: EN question
    ("How many pages long should a referatas be?", ["5–10", "5-10", "5 to 10", "five to ten", "5 – 10"], 5),
    ("Kiek kainuoja automobilio stovėjimas prie kolegijos?", None, None),                  # TS-02: not in the doc
]
ENGLISH_QUESTIONS = {"What font size is recommended for slide titles?", "How many pages long should a referatas be?"}


def run_f4() -> None:
    from scripts.make_test_files import F4
    folder = Path("samples/test_files")
    missing = [name for name, *_ in F4 if not (folder / name).exists()]
    if missing:
        sys.exit(f"missing {missing}: run python -m scripts.make_test_files first")
    print(f"AI: {'MOCK' if USE_MOCK_AI else GEMINI_MODEL + ' + ' + EMBEDDING_MODEL}  (F4, 10 documents selected)\n")
    engine = get_engine()
    passed, slowest = 0, 0.0
    with Session(engine) as session:
        department_id = session.scalar(select(Department.department_id).limit(1))
        user = register_user(session, email=f"gold-{uuid.uuid4().hex[:8]}@test.lt", password="Test1234!",
                             first_name="Gold", last_name="F4", department_id=department_id)
        user_id = user.user_id
        try:
            ids = {}
            for name, *_ in F4:
                document = upload_document(session, user, name, (folder / name).read_bytes())
                if document.status != "ready":
                    sys.exit(f"{name}: {document.status} {document.error_message or ''}")
                ids[name] = document.document_id
            for number, (name, _title, _fact, page, question, expected) in enumerate(F4, start=1):
                started = time.perf_counter()
                result = ask_question(session, user, question, list(ids.values()))
                seconds = time.perf_counter() - started
                slowest = max(slowest, seconds)
                answer = result["answer"]
                cited = [(s["document_id"], s["page"]) for s in result["sources"]]
                hit = any(e.lower() in answer.lower() for e in expected)
                right_source = (ids[name], page) in cited
                ok = hit and right_source and seconds <= LIMIT_SECONDS
                passed += ok
                names = {v: k for k, v in ids.items()}
                shown = [f"{names.get(d, d)} p.{p}" for d, p in cited]
                print(f"{'PASS' if ok else 'FAIL'}  {number:2}. {seconds:5.1f} s  {question}")
                print(f"          expected {name} p.{page}; cited {shown}"
                      f"{'' if hit else '; expected words missing'}")
                print(f"          {answer[:220].replace(chr(10), ' ')}\n")
        finally:
            session.rollback()
            paths = session.scalars(select(Document.file_path).where(Document.author_id == user_id)).all()
            session.execute(delete(User).where(User.user_id == user_id))
            session.commit()
            for path in paths:
                Path(path).unlink(missing_ok=True)
    print(f"{passed}/{len(F4)} passed (FR-02 needs >= 9), slowest answer {slowest:.1f} s (limit {LIMIT_SECONDS} s)")
    sys.exit(0 if passed >= 9 else 1)


def main() -> None:
    if "--f4" in sys.argv[1:]:
        run_f4()
        return
    print(f"AI: {'MOCK' if USE_MOCK_AI else GEMINI_MODEL + ' + ' + EMBEDDING_MODEL}\n")
    engine = get_engine()
    passed, slowest = 0, 0.0
    with Session(engine) as session:
        department_id = session.scalar(select(Department.department_id).limit(1))
        user = register_user(session, email=f"gold-{uuid.uuid4().hex[:8]}@test.lt", password="Test1234!",
                             first_name="Gold", last_name="Set", department_id=department_id)
        user_id = user.user_id
        try:
            started = time.perf_counter()
            document = upload_document(session, user, SAMPLE.name, SAMPLE.read_bytes())
            print(f"ingest: {document.status} in {time.perf_counter() - started:.1f} s"
                  f"{' – ' + document.error_message if document.error_message else ''}\n")
            if document.status != "ready":
                sys.exit(1)
            document_id = document.document_id
            for number, (question, expected, page) in enumerate(GOLD, start=1):
                started = time.perf_counter()
                result = ask_question(session, user, question, [document_id])
                seconds = time.perf_counter() - started
                slowest = max(slowest, seconds)
                answer = result["answer"]
                pages = [s["page"] for s in result["sources"]]
                if expected is None:
                    ok = not result["sources"]
                    why = "no source cited" if ok else f"cited pages {pages} for an unanswerable question"
                else:
                    hit = any(e.lower() in answer.lower() for e in expected)
                    on_page = page is None or page in pages
                    english = question in ENGLISH_QUESTIONS                           # FR-03 / TS-03
                    padded = f" {answer.lower()} "
                    right_language = (any(w in padded for w in ENGLISH_WORDS) if english
                                      else bool(LITHUANIAN_LETTERS & set(answer.lower())))
                    ok = hit and on_page and bool(pages) and right_language
                    why = ("ok" if ok else
                           f"{'' if hit else 'expected words missing; '}{'' if on_page else f'page {page} not in {pages}; '}"
                           f"{'' if right_language else 'answered in the wrong language'}")
                ok = ok and seconds <= LIMIT_SECONDS
                passed += ok
                print(f"{'PASS' if ok else 'FAIL'}  {number:2}. {seconds:5.1f} s  {question}")
                print(f"          pages {pages}  {why}")
                print(f"          {answer[:220].replace(chr(10), ' ')}\n")
        finally:
            session.rollback()
            paths = session.scalars(select(Document.file_path).where(Document.author_id == user_id)).all()
            session.execute(delete(User).where(User.user_id == user_id))
            session.commit()
            for path in paths:
                Path(path).unlink(missing_ok=True)
    print(f"{passed}/{len(GOLD)} passed, slowest answer {slowest:.1f} s (limit {LIMIT_SECONDS} s)")
    sys.exit(0 if passed == len(GOLD) else 1)


if __name__ == "__main__":
    main()
