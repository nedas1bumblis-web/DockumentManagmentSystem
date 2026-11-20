import logging
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, send_file,
                   session, url_for)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.engine import get_engine
from database.models import Category, Chunk, Department, Document, User
from processing.pdf_writer import NoFont
from security import LOCK_MINUTES, MAX_FAILED_ATTEMPTS
from services import admin as admin_service
from services.admin import ROLES, AdminError
from services.auth import login as service_login
from services.documents import (_owned_document, delete_document, parse_document_date, update_document,
                                upload_document)
from services.qa import ask_question, question_history
from services.reports import parse_period, report_csv, usage_report
from services.storage import UploadRejected
from services.summary import MAX_SUMMARY_DOCUMENTS, create_summary
from web import limiter
from web.i18n import LANG_COOKIE, LANGUAGES, current_language, gettext as _

bp = Blueprint("web", __name__)
log = logging.getLogger(__name__)

LOGIN_MESSAGES = {
    "bad_credentials": "Neteisingas slaptažodis arba el. paštas.",
    "locked": f"Paskyra užblokuota {LOCK_MINUTES} minučių po {MAX_FAILED_ATTEMPTS} nesėkmingų bandymų.",
    "inactive": "Paskyra išjungta. Kreipkitės į administratorių.",
}


def db() -> Session:
    if "db" not in g:
        g.db = Session(get_engine())
    return g.db


@bp.before_app_request
def load_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        user = db().get(User, user_id)
        if user is None or not user.is_active:
            session.clear()
        else:
            g.user = user


THEMES = {"light": "Šviesi", "dark": "Tamsi", "system": "Pagal sistemą"}
THEME_COOKIE = "theme"


@bp.app_context_processor
def preferences_context():
    chosen = request.cookies.get(THEME_COOKIE, "system")
    return {"theme": chosen if chosen in THEMES else "system", "themes": THEMES,
            "lang": current_language(), "languages": LANGUAGES, "_": _}


def _remember(cookie: str, value: str | None):
    """Cookie-stored preference (theme, language): works before login and needs no JavaScript (CSP)."""
    back = request.form.get("next", "")
    if not back.startswith("/") or back.startswith("//") or "\\" in back:     # only paths on this site
        back = url_for("web.index")
    response = redirect(back)
    if value:
        response.set_cookie(cookie, value, max_age=365 * 24 * 3600, httponly=True, samesite="Lax",
                            secure=current_app.config["SESSION_COOKIE_SECURE"])
    else:
        response.delete_cookie(cookie)
    return response


@bp.post("/theme")
def set_theme():
    """Light / dark / follow the OS."""
    chosen = request.form.get("theme", "system")
    return _remember(THEME_COOKIE, chosen if chosen in ("light", "dark") else None)


@bp.post("/language")
def set_language():
    """Interface language; Lithuanian is the default and needs no cookie."""
    chosen = request.form.get("lang", "")
    return _remember(LANG_COOKIE, chosen if chosen in LANGUAGES and chosen != "lt" else None)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("web.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user.role not in roles:
                abort(403)                                          # TS-04: "Prieiga draudžiama"
            return view(*args, **kwargs)
        return wrapped
    return decorator


admin_required = role_required("admin")
reports_required = role_required("admin", "management")            # KD 5.6: administrator and management


def categories() -> list[Category]:
    return db().scalars(select(Category).order_by(Category.category_id)).all()


def departments() -> list[Department]:
    return db().scalars(select(Department).order_by(Department.department_id)).all()


def _int_or_none(value) -> int | None:
    return int(value) if value and str(value).isdigit() else None


def owned_or_404(document_id: int) -> Document:
    try:
        return _owned_document(db(), g.user, document_id)
    except LookupError:
        abort(404)                                                  # same answer for "missing" and "not yours"


def _safe_next(target: str | None) -> str:
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("web.documents")


# ---------- login ----------

@bp.get("/")
def index():
    return redirect(url_for("web.documents" if g.user else "web.login"))


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"], methods=["POST"])   # per IP, on top of per account
def login():
    if request.method == "POST":
        status, user = service_login(db(), request.form.get("email", ""), request.form.get("password", ""))
        if status == "ok":
            session.clear()                                         # new session at login (no session fixation)
            session["user_id"] = user.user_id
            session["sid"] = secrets.token_urlsafe(16)
            session.permanent = True
            return redirect(_safe_next(request.args.get("next")))
        flash(_(LOGIN_MESSAGES[status]), "error")
        return render_template("login.html", email=request.form.get("email", "")), 401
    return render_template("login.html", email="")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.login"))


# ---------- my documents ----------

@bp.get("/documents")
@login_required
def documents():
    rows = db().scalars(select(Document).where(Document.author_id == g.user.user_id)
                        .order_by(Document.uploaded_at.desc())).all()
    all_categories = categories()
    return render_template("documents.html", documents=rows, categories=all_categories,
                           category_names={c.category_id: c.name for c in all_categories},
                           max_summary=MAX_SUMMARY_DOCUMENTS)


def _handle_upload(kind: str):
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        flash(_("Pasirinkite failą."), "error")
        return redirect(url_for("web.documents"))
    try:
        document = upload_document(db(), g.user, upload.filename, upload.read(),
                                   title=request.form.get("title") or None, kind=kind,
                                   category_id=_int_or_none(request.form.get("category_id")),
                                   document_date=parse_document_date(request.form.get("document_date")))
    except UploadRejected as exc:
        flash(_(str(exc)), "error")
        return redirect(url_for("web.documents"))
    if document.status == "ready" and kind == "summary":
        flash(_("Apibendrinimas „{title}“ išsaugotas.", title=document.title), "ok")
    elif document.status == "ready":
        flash(_("„{title}“ įkeltas ir apdorotas.", title=document.title), "ok")
    else:
        flash(_("„{title}“ nepavyko apdoroti: {error}", title=document.title, error=_(document.error_message or "")),
              "error")
    return redirect(url_for("web.documents"))


@bp.post("/documents/upload")
@login_required
def upload():
    return _handle_upload("document")


@bp.post("/summaries/upload")
@login_required
def upload_summary():                                               # FR-05, decision D4: upload only
    return _handle_upload("summary")


@bp.post("/summaries/generate")
@login_required
def generate_summary():                                             # QA A3: a PDF summary of the chosen documents
    selected = [int(x) for x in request.form.getlist("document_ids") if x.isdigit()]
    try:
        document = create_summary(db(), g.user, selected, request.form.get("language", "lt"),
                                  request.form.get("title"))
    except (UploadRejected, NoFont) as exc:
        flash(_(str(exc)), "error")
        return redirect(url_for("web.documents"))
    except Exception:
        db().rollback()
        log.exception("create_summary failed")
        flash(_("Dirbtinio intelekto paslauga laikinai nepasiekiama. Bandykite dar kartą."), "error")
        return redirect(url_for("web.documents"))
    if document.status == "ready":
        flash(_("Apibendrinimas „{title}“ sukurtas.", title=document.title), "ok")
    else:
        flash(_("„{title}“ nepavyko apdoroti: {error}", title=document.title, error=_(document.error_message or "")),
              "error")
    return redirect(url_for("web.preview", document_id=document.document_id))


@bp.get("/documents/<int:document_id>")
@login_required
def preview(document_id: int):
    document = owned_or_404(document_id)
    chunks = db().scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)).all()
    return render_template("preview.html", document=document, chunks=chunks, categories=categories(),
                           department=db().get(Department, document.department_id))


@bp.get("/documents/<int:document_id>/file")
@login_required
def download(document_id: int):
    document = owned_or_404(document_id)
    # stored paths are relative to the project root (where the server runs); Flask would resolve them against web/
    return send_file(Path(document.file_path).resolve(), as_attachment=True, download_name=f"{document.title}.{document.file_type}")


@bp.post("/documents/<int:document_id>/rename")
@login_required
def rename(document_id: int):
    """Title, and from the preview page also the metadata (KD 5.2: category, document date)."""
    owned_or_404(document_id)
    try:
        update_document(db(), g.user, document_id, title=request.form.get("title", ""),
                        category_id=_int_or_none(request.form.get("category_id")),
                        document_date=parse_document_date(request.form.get("document_date")))
    except UploadRejected as exc:
        flash(_(str(exc)), "error")
    else:
        flash(_("Pakeitimai išsaugoti.") if "category_id" in request.form else _("Pavadinimas pakeistas."), "ok")
    if request.form.get("back") == "preview":
        return redirect(url_for("web.preview", document_id=document_id))
    return redirect(url_for("web.documents"))


@bp.post("/documents/<int:document_id>/delete")
@login_required
def delete(document_id: int):
    owned_or_404(document_id)
    delete_document(db(), g.user, document_id)
    flash(_("Dokumentas ir visi jo duomenys ištrinti."), "ok")
    return redirect(url_for("web.documents"))


# ---------- questions ----------

@bp.route("/ask", methods=["GET", "POST"])
@login_required
def ask():
    all_categories = categories()
    category = _int_or_none(request.values.get("category"))          # KD 5.3.2: find documents by their metadata
    if category not in {c.category_id for c in all_categories}:
        category = None
    mine = select(Document).where(Document.author_id == g.user.user_id, Document.status == "ready")
    file_types = {d.document_id: d.file_type for d in db().scalars(mine)}
    shown = mine.where(Document.category_id == category) if category else mine
    ready = db().scalars(shown.order_by(Document.title)).all()
    result, question, selected = None, "", []
    if request.method == "POST":
        question = request.form.get("question", "")
        selected = [int(x) for x in request.form.getlist("document_ids") if x.isdigit()]
        if not selected:
            flash(_("Pasirinkite bent vieną dokumentą."), "error")
        else:
            try:
                result = ask_question(db(), g.user, question, selected)   # ownership is re-checked in SQL
            except ValueError as exc:
                flash(_(str(exc)), "error")
            except Exception:
                db().rollback()
                log.exception("ask_question failed")
                flash(_("Dirbtinio intelekto paslauga laikinai nepasiekiama. Bandykite dar kartą."), "error")
    return render_template("ask.html", documents=ready, result=result, question=question, selected=selected,
                           file_types=file_types, categories=all_categories, category=category)


@bp.get("/history")
@login_required
def history():
    return render_template("history.html", items=question_history(db(), g.user))


# ---------- admin ----------

ADMIN_PAGE_SIZE = 25
ADMIN_SORTS = {                                    # "created" first: the QA test accounts (V1, V2, A1) stay on page 1
    "created": User.user_id,
    "email": User.email,
    "name": (User.last_name, User.first_name),
}


@bp.get("/admin")
@admin_required
def admin():
    """User list with search, filters and pages, so 100+ accounts never mean scrolling to the bottom."""
    q = request.args.get("q", "").strip()[:100]
    role = request.args.get("role", "")
    status = request.args.get("status", "")
    sort = request.args.get("sort", "created")
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    now = func.now()

    doc_counts = (select(Document.author_id, func.count().label("n")).group_by(Document.author_id).subquery())
    n_docs = func.coalesce(doc_counts.c.n, 0)
    query = select(User, n_docs).outerjoin(doc_counts, doc_counts.c.author_id == User.user_id)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")   # typed % and _ are literal
        like = f"%{escaped}%"
        query = query.where(User.email.ilike(like) | (User.first_name + " " + User.last_name).ilike(like))
    if role in ("employee", "admin", "management"):
        query = query.where(User.role == role)
    if status == "locked":
        query = query.where(User.locked_until > now)
    elif status == "inactive":
        query = query.where(User.is_active.is_(False))
    elif status == "with_docs":
        query = query.where(n_docs > 0)

    total = db().scalar(select(func.count()).select_from(query.subquery()))
    pages = max((total + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE, 1)
    page = min(page, pages)
    order = n_docs.desc() if sort == "docs" else ADMIN_SORTS.get(sort, User.user_id)
    order = order if isinstance(order, tuple) else (order,)
    rows = db().execute(query.order_by(*order, User.user_id)
                        .offset((page - 1) * ADMIN_PAGE_SIZE).limit(ADMIN_PAGE_SIZE)).all()

    stats = db().execute(select(
        func.count(),
        func.count().filter(User.role == "admin"),
        func.count().filter(User.locked_until > now),
        func.count().filter(User.is_active.is_(False)),
    )).one()
    stats = dict(zip(("users", "admins", "locked", "inactive"), stats))
    stats["documents"] = db().scalar(select(func.count()).select_from(Document))

    filters = {k: v for k, v in (("q", q), ("role", role), ("status", status),
                                 ("sort", sort if sort != "created" else "")) if v}
    return render_template("admin.html", rows=rows, stats=stats, total=total, page=page, pages=pages,
                           first=(page - 1) * ADMIN_PAGE_SIZE + 1 if total else 0,
                           last=min(page * ADMIN_PAGE_SIZE, total), filters=filters,
                           q=q, role=role, status=status, sort=sort, now=datetime.now(timezone.utc))


@bp.get("/admin/users/<int:user_id>/documents")
@admin_required
def admin_user_documents(user_id: int):
    owner = db().get(User, user_id) or abort(404)
    rows = db().scalars(select(Document).where(Document.author_id == user_id)
                        .order_by(Document.uploaded_at.desc())).all()
    return render_template("admin_documents.html", owner=owner, documents=rows)


# ---------- admin: user accounts (KD 5.5) ----------

def _user_form() -> dict:
    form = request.form
    return {"first_name": form.get("first_name", ""), "last_name": form.get("last_name", ""),
            "department_id": form.get("department_id"), "role": form.get("role", "employee")}


@bp.route("/admin/users/new", methods=["GET", "POST"])
@admin_required
def admin_user_new():
    values = {"email": "", "first_name": "", "last_name": "", "department_id": None, "role": "employee"}
    if request.method == "POST":
        values = {**_user_form(), "email": request.form.get("email", "")}
        try:
            user = admin_service.create_user(db(), password=request.form.get("password", ""), **values)
        except AdminError as exc:
            flash(_(str(exc)), "error")
        else:
            flash(_("Vartotojas {email} sukurtas.", email=user.email), "ok")
            return redirect(url_for("web.admin_user_edit", user_id=user.user_id))
    return render_template("admin_user.html", user=None, values=values, departments=departments(), roles=ROLES)


@bp.route("/admin/users/<int:user_id>", methods=["GET", "POST"])
@admin_required
def admin_user_edit(user_id: int):
    user = db().get(User, user_id) or abort(404)
    values = {"email": user.email, "first_name": user.first_name, "last_name": user.last_name,
              "department_id": user.department_id, "role": user.role, "is_active": user.is_active}
    if request.method == "POST":
        values = {**values, **_user_form(), "is_active": request.form.get("is_active") == "1"}
        try:
            admin_service.update_user(db(), g.user, user_id, **{k: values[k] for k in
                                      ("first_name", "last_name", "department_id", "role", "is_active")})
        except AdminError as exc:
            db().rollback()
            flash(_(str(exc)), "error")
        else:
            flash(_("Pakeitimai išsaugoti."), "ok")
            return redirect(url_for("web.admin_user_edit", user_id=user_id))
    locked = user.locked_until is not None and user.locked_until > datetime.now(timezone.utc)
    return render_template("admin_user.html", user=user, values=values, departments=departments(), roles=ROLES,
                           locked=locked)


@bp.post("/admin/users/<int:user_id>/unlock")
@admin_required
def admin_user_unlock(user_id: int):
    try:
        admin_service.unlock_user(db(), user_id)
    except LookupError:
        abort(404)
    flash(_("Paskyra atblokuota."), "ok")
    return redirect(url_for("web.admin_user_edit", user_id=user_id))


@bp.post("/admin/users/<int:user_id>/password")
@admin_required
def admin_user_password(user_id: int):
    try:
        admin_service.set_password(db(), user_id, request.form.get("password", ""))
    except LookupError:
        abort(404)
    except AdminError as exc:
        flash(_(str(exc)), "error")
    else:
        flash(_("Slaptažodis pakeistas."), "ok")
    return redirect(url_for("web.admin_user_edit", user_id=user_id))


# ---------- admin: categories and departments ----------

@bp.get("/admin/catalog")
@admin_required
def admin_catalog():
    return render_template("admin_catalog.html", **admin_service.catalog(db()))


def _catalog_action(action, message: str):
    try:
        action()
    except LookupError:
        abort(404)
    except AdminError as exc:
        flash(_(str(exc)), "error")
    else:
        flash(_(message), "ok")
    return redirect(url_for("web.admin_catalog"))


@bp.post("/admin/categories")
@bp.post("/admin/categories/<int:category_id>")
@admin_required
def admin_category_save(category_id: int | None = None):
    form = request.form
    return _catalog_action(lambda: admin_service.save_category(db(), category_id, form.get("name", ""),
                                                               form.get("description")), "Kategorija išsaugota.")


@bp.post("/admin/categories/<int:category_id>/delete")
@admin_required
def admin_category_delete(category_id: int):
    return _catalog_action(lambda: admin_service.delete_category(db(), category_id), "Kategorija ištrinta.")


@bp.post("/admin/departments")
@bp.post("/admin/departments/<int:department_id>")
@admin_required
def admin_department_save(department_id: int | None = None):
    form = request.form
    return _catalog_action(lambda: admin_service.save_department(db(), department_id, form.get("name", ""),
                                                                 form.get("code", ""), form.get("description")),
                           "Padalinys išsaugotas.")


@bp.post("/admin/departments/<int:department_id>/delete")
@admin_required
def admin_department_delete(department_id: int):
    return _catalog_action(lambda: admin_service.delete_department(db(), department_id), "Padalinys ištrintas.")


# ---------- usage reports (KD 5.6) ----------

def _report():
    start, end = parse_period(request.args.get("from"), request.args.get("to"))
    return usage_report(db(), start, end, for_admin=g.user.role == "admin")


@bp.get("/reports")
@reports_required
def reports():
    return render_template("reports.html", report=_report())


@bp.get("/reports.csv")
@reports_required
def reports_csv():
    report = _report()
    name = f"ataskaita_{report['start']:%Y%m%d}-{report['end']:%Y%m%d}.csv"
    return Response(report_csv(report), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}"})
