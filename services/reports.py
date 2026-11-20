"""Usage reports (KD process 5.6), built from the query log (D4: queries, answers, sources).

- "Žinių bazės naudojimo ataskaita" for the management (bendro valdymo skyrius): number of questions and the most
  used documents, by category and department.
- "Sistemos naudojimo ataskaita" for the administrator: the same plus uploads and user activity.
The period ("nurodymai": laikotarpis) is chosen by the reader. Question texts are never shown: they may be private.
"""
import csv
import io
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import distinct, exists, func, select
from sqlalchemy.orm import Session

from database.models import Answer, Category, Department, Document, Source, User, UserQuery

DEFAULT_DAYS = 30
TOP = 10


def parse_period(start: str | None, end: str | None, today: date | None = None) -> tuple[date, date]:
    """Dates from the form (YYYY-MM-DD); bad or missing values fall back to the last 30 days."""
    today = today or date.today()

    def parse(value, fallback):
        try:
            return date.fromisoformat(value) if value else fallback
        except ValueError:
            return fallback

    end_date = parse(end, today)
    start_date = parse(start, end_date - timedelta(days=DEFAULT_DAYS - 1))
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    local = datetime.now().astimezone().tzinfo               # the period is in the server's local days
    return (datetime.combine(start, time.min, local).astimezone(timezone.utc),
            datetime.combine(end + timedelta(days=1), time.min, local).astimezone(timezone.utc))


def usage_report(session: Session, start: date, end: date, for_admin: bool) -> dict:
    since, until = _bounds(start, end)
    in_period = UserQuery.asked_at.between(since, until)
    has_source = exists().where(Source.answer_id == Answer.answer_id)

    queries = session.scalar(select(func.count()).select_from(UserQuery).where(in_period))
    answered = session.scalar(select(func.count()).select_from(Answer).join(UserQuery).where(in_period, has_source))
    askers = session.scalar(select(func.count(distinct(UserQuery.user_id))).where(in_period))

    cited = func.count(distinct(Source.answer_id)).label("n")
    top_documents = session.execute(
        select(Document.title, Category.name, Department.name, cited)
        .join(Source, Source.document_id == Document.document_id)
        .join(Answer, Answer.answer_id == Source.answer_id).join(UserQuery)
        .join(Category, Category.category_id == Document.category_id)
        .join(Department, Department.department_id == Document.department_id)
        .where(in_period).group_by(Document.document_id, Category.name, Department.name)
        .order_by(cited.desc(), Document.title).limit(TOP)).all()

    by_category = session.execute(
        select(Category.name, cited)
        .join(Document, Document.category_id == Category.category_id)
        .join(Source, Source.document_id == Document.document_id)
        .join(Answer, Answer.answer_id == Source.answer_id).join(UserQuery)
        .where(in_period).group_by(Category.name).order_by(cited.desc(), Category.name)).all()

    asked = func.count(UserQuery.query_id).label("n")
    by_department = session.execute(
        select(Department.name, asked, func.count(distinct(UserQuery.user_id)))
        .join(User, User.department_id == Department.department_id)
        .join(UserQuery, UserQuery.user_id == User.user_id)
        .where(in_period).group_by(Department.name).order_by(asked.desc(), Department.name)).all()

    per_day: dict[date, int] = {}                             # local calendar days (Postgres itself runs in UTC)
    for asked_at in session.scalars(select(UserQuery.asked_at).where(in_period)):
        local_day = asked_at.astimezone().date()
        per_day[local_day] = per_day.get(local_day, 0) + 1
    per_day = sorted(per_day.items())

    report = {
        "start": start, "end": end, "for_admin": for_admin,
        "queries": queries, "answered": answered, "not_found": queries - answered, "askers": askers,
        "top_documents": top_documents, "by_category": by_category, "by_department": by_department,
        "per_day": per_day,
    }
    if for_admin:
        uploaded = Document.uploaded_at.between(since, until)
        report["uploads"] = session.scalar(select(func.count()).select_from(Document).where(uploaded))
        report["uploads_failed"] = session.scalar(select(func.count()).select_from(Document)
                                                  .where(uploaded, Document.status == "failed"))
        report["documents_total"] = session.scalar(select(func.count()).select_from(Document))
        report["users_total"] = session.scalar(select(func.count()).select_from(User))
        uploads_per_user = (select(Document.author_id, func.count().label("u")).where(uploaded)
                            .group_by(Document.author_id).subquery())
        queries_per_user = (select(UserQuery.user_id, func.count().label("q")).where(in_period)
                            .group_by(UserQuery.user_id).subquery())
        q = func.coalesce(queries_per_user.c.q, 0)
        u = func.coalesce(uploads_per_user.c.u, 0)
        report["active_users"] = session.execute(
            select(User.email, Department.name, q, u)
            .join(Department, Department.department_id == User.department_id)
            .outerjoin(queries_per_user, queries_per_user.c.user_id == User.user_id)
            .outerjoin(uploads_per_user, uploads_per_user.c.author_id == User.user_id)
            .where((q > 0) | (u > 0)).order_by(q.desc(), u.desc(), User.email).limit(TOP)).all()
    return report


def report_csv(report: dict) -> str:
    """The report as CSV (Excel opens it: UTF-8 with BOM, ';' as the separator Lithuanian Excel expects)."""
    out = io.StringIO()
    out.write("﻿")
    w = csv.writer(out, delimiter=";", lineterminator="\r\n")
    w.writerow(["Laikotarpis", report["start"].isoformat(), report["end"].isoformat()])
    w.writerow([])
    w.writerow(["Rodiklis", "Reikšmė"])
    rows = [("Klausimų", report["queries"]), ("Atsakyta su šaltiniu", report["answered"]),
            ("Informacijos nerasta", report["not_found"]), ("Klaususių vartotojų", report["askers"])]
    if report["for_admin"]:
        rows += [("Įkelta dokumentų", report["uploads"]), ("Nepavyko apdoroti", report["uploads_failed"]),
                 ("Dokumentų iš viso", report["documents_total"]), ("Vartotojų iš viso", report["users_total"])]
    w.writerows(rows)
    w.writerow([])
    w.writerow(["Dažniausiai naudojami dokumentai", "Kategorija", "Padalinys", "Atsakymų"])
    w.writerows(report["top_documents"])
    w.writerow([])
    w.writerow(["Kategorija", "Atsakymų"])
    w.writerows(report["by_category"])
    w.writerow([])
    w.writerow(["Padalinys", "Klausimų", "Klaususių vartotojų"])
    w.writerows(report["by_department"])
    w.writerow([])
    w.writerow(["Diena", "Klausimų"])
    w.writerows((d.isoformat(), n) for d, n in report["per_day"])
    if report["for_admin"]:
        w.writerow([])
        w.writerow(["Aktyviausi vartotojai", "Padalinys", "Klausimų", "Įkėlė dokumentų"])
        w.writerows(report["active_users"])
    return out.getvalue()
