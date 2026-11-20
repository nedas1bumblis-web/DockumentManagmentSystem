from decimal import Decimal

from sqlalchemy.orm import Session

from app_config import GEMINI_MODEL, USE_MOCK_AI
from database.models import Answer, Source, User, UserQuery
from rag.embedder import embed_texts
from rag.llm import generate_answer
from rag.prompt import detect_language, parse_citations
from rag.retrieval import search_chunks

MAX_QUESTION_CHARS = 2000
NOT_FOUND = {"lt": "Pasirinktuose dokumentuose tokios informacijos nėra.",          # FR-03: in the question's language
             "en": "The selected documents do not contain this information."}


def ask_question(session: Session, user: User, question: str, document_ids: list[int]) -> dict:
    question = question.strip()
    if not question:
        raise ValueError("Klausimas tuščias.")
    if len(question) > MAX_QUESTION_CHARS:
        raise ValueError(f"Klausimas ilgesnis nei {MAX_QUESTION_CHARS} simbolių.")

    user_id = user.user_id
    query_vector = embed_texts([question], "RETRIEVAL_QUERY")[0]
    hits = search_chunks(session, query_vector, user_id, document_ids)
    session.commit()          # ends the read transaction: the DB connection goes back to the pool while we wait for Gemini
    answer_text = generate_answer(question, hits) if hits else NOT_FOUND[detect_language(question)]
    cited = parse_citations(answer_text, len(hits))

    sources, seen = [], set()
    for number in cited:
        hit = hits[number - 1]
        key = (hit["document_id"], hit["page"])
        if key not in seen:
            seen.add(key)
            sources.append({"document_id": hit["document_id"], "document": hit["document"], "page": hit["page"]})

    confidence = None
    if cited:
        best = max(hits[n - 1]["similarity"] for n in cited)
        confidence = Decimal(str(round(min(max(best, 0.0), 1.0) * 100, 2)))

    asked = UserQuery(user_id=user_id, question_text=question)
    session.add(asked)
    session.flush()                                                      # gives `asked` its query_id
    answer = Answer(query_id=asked.query_id, answer_text=answer_text, confidence=confidence,
                    model_name="mock" if USE_MOCK_AI else GEMINI_MODEL)
    session.add(answer)
    session.flush()
    session.add_all(Source(answer_id=answer.answer_id, document_id=s["document_id"], page_number=s["page"])
                    for s in sources)
    session.commit()
    return {"answer": answer_text, "sources": sources, "confidence": confidence}


HISTORY_SIZE = 50


def question_history(session: Session, user: User, limit: int = HISTORY_SIZE) -> list[dict]:
    """KD use case "atsakymo peržiūra": the user's latest questions from the query log, newest first."""
    from sqlalchemy import select
    from database.models import Document

    rows = session.execute(select(UserQuery, Answer).join(Answer, Answer.query_id == UserQuery.query_id)
                           .where(UserQuery.user_id == user.user_id)
                           .order_by(UserQuery.asked_at.desc(), UserQuery.query_id.desc()).limit(limit)).all()
    answer_ids = [a.answer_id for _, a in rows]
    cited: dict[int, list[dict]] = {}
    if answer_ids:
        for answer_id, document_id, title, file_type, page in session.execute(
                select(Source.answer_id, Document.document_id, Document.title, Document.file_type, Source.page_number)
                .join(Document, Document.document_id == Source.document_id)
                .where(Source.answer_id.in_(answer_ids)).order_by(Source.source_id)):
            cited.setdefault(answer_id, []).append(
                {"document_id": document_id, "document": title, "file_type": file_type, "page": page})
    return [{"question": q.question_text, "asked_at": q.asked_at, "answer": a.answer_text,
             "confidence": a.confidence, "sources": cited.get(a.answer_id, [])} for q, a in rows]
