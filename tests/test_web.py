"""Web layer against the real Postgres, with the offline mock AI. Skipped when the database is not reachable.

Covers the web parts of TS-01 (upload, preview, rename, ask), TS-04 (403, other users' documents) and
TS-05 (lockout messages, cookie flags), plus the phase 7 checklist (CSRF, escaping, headers, size limit).
"""
import io
import re
import uuid
from pathlib import Path

import pytest
from docx import Document as new_docx

pytest.importorskip("flask")

from sqlalchemy import delete, select, text                     # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from database.engine import get_engine                           # noqa: E402
from database.models import Department, Document, User          # noqa: E402

PASSWORD = "Test1234!"
REFERER = {"Referer": "https://localhost/"}      # Flask-WTF checks it on HTTPS, as browsers send it


def _db_available() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("select 1 from users limit 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable (start Docker, run init_db)")


@pytest.fixture(scope="module")
def users():
    from services.auth import register_user
    tag = uuid.uuid4().hex[:8]
    with Session(get_engine()) as session:
        department_id = session.scalar(select(Department.department_id).limit(1))
        made = {name: register_user(session, email=f"web-{name}-{tag}@test.lt", password=PASSWORD, first_name="W",
                                    last_name=name, department_id=department_id, role=role)
                for name, role in (("v1", "employee"), ("v2", "employee"), ("admin", "admin"), ("lock", "employee"))}
        info = {name: (u.user_id, u.email) for name, u in made.items()}
    yield info
    with Session(get_engine()) as session:
        ids = [user_id for user_id, _ in info.values()]
        paths = session.scalars(select(Document.file_path).where(Document.author_id.in_(ids))).all()
        session.execute(delete(User).where(User.user_id.in_(ids)))
        session.commit()
    for path in paths:
        Path(path).unlink(missing_ok=True)


@pytest.fixture()
def app(monkeypatch):
    import rag.embedder
    import rag.llm
    import services.qa
    for module in (rag.embedder, rag.llm, services.qa):
        monkeypatch.setattr(module, "USE_MOCK_AI", True)
    from web import create_app
    return create_app({"TESTING": True, "SECRET_KEY": "test-secret", "LOGIN_RATE_LIMIT": "1000 per minute"})


def client_for(app, ip="10.0.0.1"):
    client = app.test_client()
    client.environ_base["REMOTE_ADDR"] = ip
    return client


def csrf(client, path="/login") -> str:
    page = client.get(path, base_url="https://localhost").get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)


def post(client, path, data, token_page="/documents", **kwargs):
    data = {"csrf_token": csrf(client, token_page), **data}
    return client.post(path, data=data, base_url="https://localhost", headers=REFERER, **kwargs)


def get(client, path):
    return client.get(path, base_url="https://localhost")


def log_in(client, email, password=PASSWORD):
    return post(client, "/login", {"email": email, "password": password}, token_page="/login")


def docx_file(text_: str, name="policy.docx"):
    buffer = io.BytesIO()
    doc = new_docx()
    doc.add_paragraph(text_)
    doc.save(buffer)
    buffer.seek(0)
    return buffer, name


# ---------- theme switch ----------

def test_theme_switch_is_remembered_and_safe(app):
    client = client_for(app)
    page = get(client, "/login").get_data(as_text=True)
    assert "data-theme" not in page and 'value="system" aria-pressed="true"' in page        # default: follow the OS

    response = post(client, "/theme", {"theme": "dark", "next": "/login"}, token_page="/login")
    assert response.status_code == 302 and response.headers["Location"].endswith("/login")
    cookie = response.headers["Set-Cookie"]
    assert "theme=dark" in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert '<html lang="lt" data-theme="dark">' in get(client, "/login").get_data(as_text=True)

    post(client, "/theme", {"theme": "light", "next": "/login"}, token_page="/login")
    assert 'data-theme="light"' in get(client, "/login").get_data(as_text=True)
    post(client, "/theme", {"theme": "system", "next": "/login"}, token_page="/login")
    assert "data-theme" not in get(client, "/login").get_data(as_text=True)

    for evil in ("https://evil.example/", "//evil.example/", "/\\evil.example"):                # no open redirect
        response = post(client, "/theme", {"theme": "dark", "next": evil}, token_page="/login")
        assert "evil" not in response.headers["Location"]
    client.set_cookie("theme", "<script>", domain="localhost")                                 # junk cookie
    assert "<script>" not in get(client, "/login").get_data(as_text=True).split("<body>")[0]
    no_token = client.post("/theme", data={"theme": "dark"}, base_url="https://localhost", headers=REFERER)
    assert no_token.status_code == 400                                                         # CSRF still applies


# ---------- interface language ----------

LT_LETTERS = re.compile(r"[ąčęėįšųūžĄČĘĖĮŠŲŪŽ„]")             # „ opens a Lithuanian quote


def _visible_text(html: str) -> str:
    html = re.sub(r'<span class="brand-mark">Ž</span>|<div class="brand-mark">Ž</div>', "", html)
    html = re.sub(r"<(script|style|textarea|select)\b.*?</\1>", "", html, flags=re.S)   # select: category names = data
    return re.sub(r"<[^>]+>", " ", html)


def test_every_interface_text_has_an_english_translation():
    from web.i18n import EN
    root = Path(__file__).resolve().parent.parent / "web"
    texts = set()
    for path in [*root.glob("templates/*.html"), root / "views.py", root / "__init__.py"]:
        source = path.read_text(encoding="utf-8")
        texts |= set(re.findall(r"""_\(\s*'([^']+)'""", source)) | set(re.findall(r'''_\(\s*"([^"]+)"''', source))
        # labels translated through a variable: _(label), _(status_labels[...]), _(role_labels[...])
        for block in re.findall(r"\{%\s*(?:set \w+_labels = \{|for [^%]*in \[)(.*?)%\}", source, re.S):
            texts |= {t for t in re.findall(r"'([^']+)'", block)
                      if not re.fullmatch(r"[a-z_]+", t) and re.search(r"[^\W\d_]", t)}          # skip keys and icons
    from web.views import LOGIN_MESSAGES
    texts |= set(LOGIN_MESSAGES.values())
    missing = sorted(t for t in texts if t not in EN)
    assert not missing, f"no English for: {missing}"


def test_language_switch_translates_every_page(app, users):
    client = client_for(app, ip="10.0.0.7")
    page = get(client, "/login").get_data(as_text=True)
    assert '<html lang="lt"' in page and "Prisijungimas" in page                              # default: Lithuanian
    response = post(client, "/language", {"lang": "en", "next": "/login"}, token_page="/login")
    assert response.status_code == 302 and "lang=en" in response.headers["Set-Cookie"]
    page = get(client, "/login").get_data(as_text=True)
    assert '<html lang="en"' in page and "Sign in" in page and not LT_LETTERS.search(_visible_text(page))

    response = log_in(client, users["admin"][1])
    buffer, name = docx_file("Annual leave lasts 20 working days.", "leave.docx")
    response = post(client, "/documents/upload", {"file": (buffer, name)}, content_type="multipart/form-data")
    page = client.get(response.headers["Location"], base_url="https://localhost").get_data(as_text=True)
    assert "“leave” uploaded and processed." in page
    doc = re.search(r'href="/documents/(\d+)">leave<', page).group(1)
    answered = post(client, "/ask", {"question": "How long is annual leave?", "document_ids": doc}, token_page="/ask")
    pages = {
        "/documents": page,
        "/ask (answer)": answered.get_data(as_text=True),
        f"/documents/{doc}": get(client, f"/documents/{doc}").get_data(as_text=True),
        "/admin": get(client, f"/admin?q={users['admin'][1]}").get_data(as_text=True),
        "/admin/users": get(client, f"/admin/users/{users['admin'][0]}/documents").get_data(as_text=True),
        "404": get(client, "/documents/999999999").get_data(as_text=True),
    }
    for where, html in pages.items():
        leftover = LT_LETTERS.findall(_visible_text(html))
        assert not leftover, f"Lithuanian text left on {where}: {leftover}"
    assert "Not found" in pages["404"] and "Answer" in pages["/ask (answer)"]

    post(client, "/language", {"lang": "lt", "next": "/documents"})                            # back to Lithuanian
    assert "Mano dokumentai" in get(client, "/documents").get_data(as_text=True)
    post(client, f"/documents/{doc}/delete", {})


def test_not_found_answer_follows_the_question_language():
    from services.qa import NOT_FOUND
    from rag.prompt import detect_language
    assert NOT_FOUND[detect_language("Who is the director?")].startswith("The selected documents")
    assert NOT_FOUND[detect_language("Kas yra direktorius?")].startswith("Pasirinktuose dokumentuose")


# ---------- login, cookies, headers ----------

def test_login_page_has_security_headers(app):
    response = get(client_for(app), "/login")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Strict-Transport-Security"]


def test_post_without_csrf_token_is_rejected(app, users):
    response = client_for(app).post("/login", data={"email": users["v1"][1], "password": PASSWORD},
                                    base_url="https://localhost")
    assert response.status_code == 400


def test_wrong_password_message(app, users):
    response = log_in(client_for(app), users["v1"][1], "Klaida111")
    assert response.status_code == 401
    assert "Neteisingas slaptažodis" in response.get_data(as_text=True)


def test_login_sets_hardened_cookie_and_redirects(app, users):
    response = log_in(client_for(app), users["v1"][1])
    assert response.status_code == 302 and response.headers["Location"].endswith("/documents")
    cookie = response.headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_open_redirect_after_login_is_blocked(app, users):
    client = client_for(app)
    response = client.post("/login?next=//evil.example", base_url="https://localhost", headers=REFERER,
                           data={"csrf_token": csrf(client), "email": users["v1"][1], "password": PASSWORD})
    assert response.headers["Location"].endswith("/documents")


def test_lockout_message_after_five_failures(app, users):
    client = client_for(app)
    for _ in range(4):
        log_in(client, users["lock"][1], "Klaida111")
    body = log_in(client, users["lock"][1], "Klaida111").get_data(as_text=True)
    assert "užblokuota 15 minučių" in body
    assert "užblokuota" in log_in(client, users["lock"][1]).get_data(as_text=True)   # right password refused too


def test_login_is_rate_limited_per_ip(monkeypatch):
    import rag.embedder  # noqa: F401  (same import side effects as the app fixture)
    from web import create_app
    limited = create_app({"TESTING": True, "SECRET_KEY": "test-secret", "LOGIN_RATE_LIMIT": "3 per minute"})
    client = client_for(limited, ip="10.9.9.9")
    codes = [log_in(client, "nobody@test.lt", "Klaida111").status_code for _ in range(4)]
    assert codes[:3] == [401, 401, 401] and codes[3] == 429


def test_pages_need_login(app):
    for path in ("/documents", "/ask", "/admin", "/documents/1"):
        response = get(client_for(app), path)
        assert response.status_code == 302 and "/login" in response.headers["Location"]


# ---------- TS-01: upload, preview, rename, ask, delete ----------

def test_document_lifecycle_and_isolation(app, users):
    v1, v2 = client_for(app), client_for(app, ip="10.0.0.2")
    log_in(v1, users["v1"][1])
    log_in(v2, users["v2"][1])

    response = post(v1, "/documents/upload", {"file": docx_file("Atostogos trunka 28 kalendorines dienas per metus.")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert "įkeltas ir apdorotas" in response.get_data(as_text=True)
    post(v2, "/documents/upload", {"file": docx_file("Travel expenses up to 100 EUR per day.", "travel.docx")},
         content_type="multipart/form-data")

    with Session(get_engine()) as session:
        d1 = session.scalar(select(Document).where(Document.author_id == users["v1"][0]))
        d2 = session.scalar(select(Document).where(Document.author_id == users["v2"][0]))
    assert d1.status == "ready" and d2.status == "ready"

    listing = get(v1, "/documents").get_data(as_text=True)
    assert "policy" in listing and "travel" not in listing                 # only my documents

    preview = get(v1, f"/documents/{d1.document_id}")
    assert preview.status_code == 200 and "28 kalendorines" in preview.get_data(as_text=True)
    assert "≈ p." in preview.get_data(as_text=True)                         # decision D3 label for DOCX
    assert get(v1, f"/documents/{d1.document_id}/file").status_code == 200

    # TS-04 / IDOR: another user's document by URL, by download, by rename, by delete, by question
    assert get(v1, f"/documents/{d2.document_id}").status_code == 404
    assert get(v1, f"/documents/{d2.document_id}/file").status_code == 404
    assert post(v1, f"/documents/{d2.document_id}/rename", {"title": "x"}).status_code == 404
    assert post(v1, f"/documents/{d2.document_id}/delete", {}).status_code == 404
    stolen = post(v1, "/ask", {"question": "travel expenses per day", "document_ids": [str(d2.document_id)]},
                  token_page="/ask").get_data(as_text=True)
    assert "100 EUR" not in stolen

    # rename, and the title is escaped when shown (XSS)
    post(v1, f"/documents/{d1.document_id}/rename", {"title": "<script>alert(1)</script>"})
    listing = get(v1, "/documents").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in listing and "&lt;script&gt;" in listing

    answer = post(v1, "/ask", {"question": "Kiek dienų trunka atostogos?", "document_ids": [str(d1.document_id)]},
                  token_page="/ask").get_data(as_text=True)
    assert "Šaltiniai" in answer and "28 kalendorines" in answer and "Paieškos panašumas" in answer

    deleted = post(v1, f"/documents/{d1.document_id}/delete", {}, follow_redirects=True)
    assert "ištrinti" in deleted.get_data(as_text=True)
    assert get(v1, f"/documents/{d1.document_id}").status_code == 404
    assert not Path(d1.file_path).exists()


def test_summary_upload_is_stored_as_summary(app, users):
    client = client_for(app)
    log_in(client, users["v1"][1])
    page = post(client, "/summaries/upload", {"file": docx_file("Santrauka.", "santrauka.docx")},
                content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "Apibendrinimas „santrauka“ išsaugotas" in page                 # TS-01 step 4
    assert page.index("Apibendrinimai") < page.index(">santrauka<")         # listed under "Apibendrinimai"
    with Session(get_engine()) as session:
        kinds = session.scalars(select(Document.kind).where(Document.author_id == users["v1"][0])).all()
    assert "summary" in kinds


def test_wrong_file_type_is_rejected_with_a_message(app, users):
    client = client_for(app)
    log_in(client, users["v1"][1])
    response = post(client, "/documents/upload", {"file": (io.BytesIO(b"MZ\x90\x00"), "virus.pdf")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert "neatitinka jo plėtinio" in response.get_data(as_text=True)


def test_document_limit_per_user(app, users, monkeypatch):                # FR-08 / TS-07 (limit lowered to 2)
    import services.documents
    monkeypatch.setattr(services.documents, "MAX_DOCUMENTS_PER_USER", 2)
    client = client_for(app, ip="10.0.0.3")
    log_in(client, users["v2"][1])                     # v2 already owns travel.docx from the lifecycle test
    post(client, "/documents/upload", {"file": docx_file("Antras.", "antras.docx")}, content_type="multipart/form-data")
    page = post(client, "/documents/upload", {"file": docx_file("Trečias.", "trecias.docx")},
                content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "ne daugiau kaip 2 dokumentų" in page and "trecias" not in page


def test_oversize_upload_is_refused_before_the_view(app, users):
    client = client_for(app)
    log_in(client, users["v1"][1])
    token = csrf(client, "/documents")
    big = io.BytesIO(b"%PDF-" + b"0" * (22 * 1024 * 1024))
    response = client.post("/documents/upload", data={"csrf_token": token, "file": (big, "big.pdf")},
                           content_type="multipart/form-data", base_url="https://localhost", headers=REFERER)
    assert response.status_code == 413


# ---------- TS-04: admin ----------

def test_admin_panel_is_forbidden_for_users_and_hidden_in_menu(app, users):
    client = client_for(app)
    log_in(client, users["v1"][1])
    assert "Admin panelė" not in get(client, "/documents").get_data(as_text=True)
    response = get(client, "/admin")
    assert response.status_code == 403 and "Prieiga draudžiama" in response.get_data(as_text=True)
    assert get(client, f"/admin/users/{users['v2'][0]}/documents").status_code == 403


def test_admin_sees_the_panel(app, users):
    client = client_for(app)
    log_in(client, users["admin"][1])
    assert "Admin panelė" in get(client, "/documents").get_data(as_text=True)
    page = get(client, f"/admin?q={users['v1'][1]}")
    assert page.status_code == 200 and users["v1"][1] in page.get_data(as_text=True)
    assert get(client, f"/admin/users/{users['v1'][0]}/documents").status_code == 200


def test_admin_list_is_paged_and_searchable(app, users):
    from web.views import ADMIN_PAGE_SIZE
    client = client_for(app)
    log_in(client, users["admin"][1])
    with Session(get_engine()) as session:
        total = session.scalar(select(text("count(*)")).select_from(User))
    page = get(client, "/admin").get_data(as_text=True)
    assert page.count('<td class="title">') == min(total, ADMIN_PAGE_SIZE)            # one page, not every user
    assert f"iš {total}" in page
    last = get(client, "/admin?page=9999").get_data(as_text=True)                      # past the end -> last page
    assert last.count('<td class="title">') == total - (max(total - 1, 0) // ADMIN_PAGE_SIZE) * ADMIN_PAGE_SIZE

    tag = users["v1"][1].split("-")[-1].split("@")[0]                                  # this run's accounts only
    found = get(client, f"/admin?q={tag}").get_data(as_text=True)
    assert found.count('<td class="title">') == 4 and users["v2"][1] in found
    admins = get(client, f"/admin?q={tag}&role=admin").get_data(as_text=True)
    assert admins.count('<td class="title">') == 1 and users["admin"][1] in admins
    literal = get(client, "/admin?q=%25%25%25").get_data(as_text=True)                 # "%" is not a wildcard
    assert "Nieko nerasta" in literal
    assert get(client, "/admin?page=abc&sort=drop+table").status_code == 200           # junk input is ignored


def test_logout_ends_the_session(app, users):
    client = client_for(app)
    log_in(client, users["v1"][1])
    post(client, "/logout", {})
    assert get(client, "/documents").status_code == 302


# ---------- KD 5.2 / 5.3.2: metadata and search by category ----------

def _category_id(name: str) -> int:
    from database.models import Category
    with Session(get_engine()) as session:
        return session.scalar(select(Category.category_id).where(Category.name == name))


def _my_documents(user_id: int) -> list[Document]:
    with Session(get_engine()) as session:
        return session.scalars(select(Document).where(Document.author_id == user_id)
                               .order_by(Document.document_id)).all()


def test_upload_with_metadata_and_edit_it(app, users):
    client = client_for(app, ip="10.0.1.1")
    log_in(client, users["v1"][1])
    contracts, manuals = _category_id("Sutartys"), _category_id("Instrukcijos")
    before = {d.document_id for d in _my_documents(users["v1"][0])}
    page = post(client, "/documents/upload", {"file": docx_file("Sutartis galioja 2 metus.", "sutartis.docx"),
                                              "category_id": str(contracts), "document_date": "2025-01-15"},
                content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "įkeltas ir apdorotas" in page and ">Sutartys<" in page
    doc = next(d for d in _my_documents(users["v1"][0]) if d.document_id not in before)
    assert (doc.category_id, doc.document_date.isoformat()) == (contracts, "2025-01-15")

    post(client, f"/documents/{doc.document_id}/rename",
         {"title": "Sutartis", "category_id": str(manuals), "document_date": "2025-02-01", "back": "preview"})
    changed = next(d for d in _my_documents(users["v1"][0]) if d.document_id == doc.document_id)
    assert (changed.title, changed.category_id, changed.document_date.isoformat()) == ("Sutartis", manuals, "2025-02-01")
    preview = get(client, f"/documents/{doc.document_id}").get_data(as_text=True)
    assert "Padalinys" in preview and 'value="2025-02-01"' in preview

    future = post(client, "/documents/upload", {"file": docx_file("X.", "x.docx"), "document_date": "2999-01-01"},
                  content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "negali būti ateityje" in future
    missing = post(client, "/documents/upload", {"file": docx_file("Y.", "y.docx"), "category_id": "999999"},
                   content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "Tokios kategorijos nėra" in missing
    post(client, f"/documents/{doc.document_id}/delete", {})


def test_ask_page_filters_documents_by_category(app, users):
    client = client_for(app, ip="10.0.1.2")
    log_in(client, users["v1"][1])
    reports, contracts = _category_id("Ataskaitos"), _category_id("Sutartys")
    before = {d.document_id for d in _my_documents(users["v1"][0])}
    post(client, "/documents/upload", {"file": docx_file("Metinė ataskaita.", "ataskaita.docx"),
                                       "category_id": str(reports)}, content_type="multipart/form-data")
    post(client, "/documents/upload", {"file": docx_file("Nuomos sutartis.", "nuoma.docx"),
                                       "category_id": str(contracts)}, content_type="multipart/form-data")
    only_reports = get(client, f"/ask?category={reports}").get_data(as_text=True)
    assert "ataskaita</label>" in only_reports and "nuoma</label>" not in only_reports
    everything = get(client, "/ask").get_data(as_text=True)
    assert "ataskaita</label>" in everything and "nuoma</label>" in everything
    for d in _my_documents(users["v1"][0]):
        if d.document_id not in before:
            post(client, f"/documents/{d.document_id}/delete", {})


# ---------- QA A3: generated PDF summary ----------

def test_generated_summary_is_a_searchable_pdf(app, users):
    from processing.pdf_writer import NoFont, find_fonts
    try:
        find_fonts()
    except NoFont:
        pytest.skip("no TrueType font on this machine")
    v1, v2 = client_for(app, ip="10.0.1.3"), client_for(app, ip="10.0.1.4")
    log_in(v1, users["v1"][1])
    log_in(v2, users["v2"][1])
    before = {d.document_id for d in _my_documents(users["v1"][0])}
    post(v1, "/documents/upload", {"file": docx_file("Kasmetinės atostogos trunka 20 darbo dienų.", "atostogos.docx")},
         content_type="multipart/form-data")
    source = next(d for d in _my_documents(users["v1"][0]) if d.document_id not in before)

    response = post(v1, "/summaries/generate", {"document_ids": [str(source.document_id)], "language": "lt",
                                                "title": "Atostogų santrauka"})
    assert response.status_code == 302 and "/documents/" in response.headers["Location"]
    page = get(v1, response.headers["Location"]).get_data(as_text=True)
    assert "Apibendrinimas „Atostogų santrauka“ sukurtas" in page and "20 darbo dienų" in page
    summary = next(d for d in _my_documents(users["v1"][0]) if d.title == "Atostogų santrauka")
    assert (summary.kind, summary.file_type, summary.status) == ("summary", "pdf", "ready")
    assert Path(summary.file_path).read_bytes().startswith(b"%PDF-")
    listing = get(v1, "/documents").get_data(as_text=True)
    assert listing.index("Apibendrinimai") < listing.index(">Atostogų santrauka<")

    stolen = post(v2, "/summaries/generate", {"document_ids": [str(source.document_id)]}, follow_redirects=True)
    assert "Pasirinkite bent vieną dokumentą" in stolen.get_data(as_text=True)      # someone else's document
    assert "Pasirinkite bent vieną" in post(v1, "/summaries/generate", {}, follow_redirects=True).get_data(as_text=True)
    for d in (summary, source):
        post(v1, f"/documents/{d.document_id}/delete", {})


# ---------- KD use case "atsakymo peržiūra": history ----------

def test_history_lists_my_questions_only(app, users):
    v1, v2 = client_for(app, ip="10.0.1.5"), client_for(app, ip="10.0.1.6")
    log_in(v1, users["v1"][1])
    log_in(v2, users["v2"][1])
    before = {d.document_id for d in _my_documents(users["v1"][0])}
    post(v1, "/documents/upload", {"file": docx_file("Darbo laikas nuo 8 iki 17 valandos.", "darbo_laikas.docx")},
         content_type="multipart/form-data")
    doc = next(d for d in _my_documents(users["v1"][0]) if d.document_id not in before)
    post(v1, "/ask", {"question": "Koks darbo laikas istorijai?", "document_ids": [str(doc.document_id)]},
         token_page="/ask")
    mine = get(v1, "/history").get_data(as_text=True)
    assert "Koks darbo laikas istorijai?" in mine and ">darbo_laikas<" in mine
    assert "Koks darbo laikas istorijai?" not in get(v2, "/history").get_data(as_text=True)
    post(v1, f"/documents/{doc.document_id}/delete", {})
    assert "Koks darbo laikas istorijai?" not in get(v1, "/history").get_data(as_text=True)   # erased with the doc


# ---------- KD 5.5: user accounts managed by the administrator ----------

def test_admin_pages_are_forbidden_for_users(app, users):
    client = client_for(app, ip="10.0.1.7")
    log_in(client, users["v1"][1])
    for path in ("/admin/users/new", f"/admin/users/{users['v2'][0]}", "/admin/catalog", "/reports", "/reports.csv"):
        assert get(client, path).status_code == 403, path
    assert post(client, "/admin/categories", {"name": "X"}).status_code == 403
    assert post(client, f"/admin/users/{users['v1'][0]}/unlock", {}).status_code == 403
    assert 'href="/reports"' not in get(client, "/documents").get_data(as_text=True)


def test_admin_creates_edits_locks_out_and_disables_a_user(app, users):
    admin = client_for(app, ip="10.0.1.8")
    log_in(admin, users["admin"][1])
    email = f"new-{uuid.uuid4().hex[:8]}@test.lt"
    with Session(get_engine()) as session:
        department_id = session.scalar(select(Department.department_id).where(Department.code == "PER"))
    response = post(admin, "/admin/users/new", {"email": email.upper(), "first_name": "Ona", "last_name": "Onaitė",
                                                "department_id": str(department_id), "role": "employee",
                                                "password": "Laikinas1!"}, token_page="/admin/users/new")
    assert response.status_code == 302
    with Session(get_engine()) as session:
        user = session.scalar(select(User).where(User.email == email))
    assert user and user.department_id == department_id and user.password_hash.startswith("$2b$")
    edit = f"/admin/users/{user.user_id}"
    try:
        again = post(admin, "/admin/users/new", {"email": email, "first_name": "A", "last_name": "B",
                                                 "department_id": str(department_id), "role": "employee",
                                                 "password": "Laikinas1!"}, token_page="/admin/users/new")
        assert "jau yra" in again.get_data(as_text=True)
        short = post(admin, "/admin/users/new", {"email": "x" + email, "first_name": "A", "last_name": "B",
                                                 "department_id": str(department_id), "role": "employee",
                                                 "password": "trumpas"}, token_page="/admin/users/new")
        assert "ne trumpesnis nei 8" in short.get_data(as_text=True)

        newcomer = client_for(app, ip="10.0.1.9")
        assert log_in(newcomer, email, "Laikinas1!").status_code == 302                  # can sign in at once

        post(admin, edit, {"first_name": "Ona", "last_name": "Onaitė", "department_id": str(department_id),
                           "role": "management", "is_active": "1"}, token_page=edit)
        assert get(newcomer, "/reports").status_code == 200                              # new rights at once
        assert get(newcomer, "/admin").status_code == 403

        for _ in range(5):
            log_in(client_for(app, ip="10.0.1.10"), email, "Klaida111")
        assert "užblokuota" in get(admin, edit).get_data(as_text=True)
        post(admin, f"{edit}/unlock", {}, token_page=edit)
        assert log_in(client_for(app, ip="10.0.1.11"), email, "Laikinas1!").status_code == 302

        post(admin, f"{edit}/password", {"password": "Naujas123!"}, token_page=edit)
        assert log_in(client_for(app, ip="10.0.1.12"), email, "Naujas123!").status_code == 302

        post(admin, edit, {"first_name": "Ona", "last_name": "Onaitė", "department_id": str(department_id),
                           "role": "management"}, token_page=edit)                       # checkbox off = disabled
        assert get(newcomer, "/documents").status_code == 302                            # thrown out
        assert "išjungta" in log_in(client_for(app, ip="10.0.1.13"), email, "Naujas123!").get_data(as_text=True)

        own = f"/admin/users/{users['admin'][0]}"
        refused = post(admin, own, {"first_name": "W", "last_name": "admin", "department_id": str(department_id),
                                    "role": "employee", "is_active": "1"}, token_page=own, follow_redirects=True)
        assert "Negalite atimti" in refused.get_data(as_text=True)
        assert get(admin, "/admin").status_code == 200                                    # still an admin
    finally:
        with Session(get_engine()) as session:
            session.execute(delete(User).where(User.email == email))
            session.commit()


def test_admin_manages_categories_and_departments(app, users):
    from database.models import Category
    admin = client_for(app, ip="10.0.1.14")
    log_in(admin, users["admin"][1])
    name, code = f"Kat-{uuid.uuid4().hex[:6]}", f"T{uuid.uuid4().hex[:5]}".upper()
    post(admin, "/admin/categories", {"name": name, "description": "Testas"}, token_page="/admin/catalog")
    page = get(admin, "/admin/catalog").get_data(as_text=True)
    assert f'value="{name}"' in page
    category_id = _category_id(name)
    post(admin, f"/admin/categories/{category_id}", {"name": name + "2"}, token_page="/admin/catalog")
    assert _category_id(name + "2") == category_id
    duplicate = post(admin, "/admin/categories", {"name": "Sutartys"}, token_page="/admin/catalog",
                     follow_redirects=True)
    assert "jau yra" in duplicate.get_data(as_text=True)
    post(admin, f"/admin/categories/{category_id}/delete", {}, token_page="/admin/catalog")
    assert _category_id(name + "2") is None
    with Session(get_engine()) as session:
        default = session.scalar(select(Category.category_id).order_by(Category.category_id).limit(1))
    refused = post(admin, f"/admin/categories/{default}/delete", {}, token_page="/admin/catalog", follow_redirects=True)
    assert "Numatytosios kategorijos ištrinti negalima" in refused.get_data(as_text=True)

    post(admin, "/admin/departments", {"name": "Testų skyrius", "code": code}, token_page="/admin/catalog")
    with Session(get_engine()) as session:
        department = session.scalar(select(Department).where(Department.code == code))
    assert department is not None
    with Session(get_engine()) as session:
        used = session.scalar(select(Department.department_id).where(Department.code == "GEN"))
    refused = post(admin, f"/admin/departments/{used}/delete", {}, token_page="/admin/catalog", follow_redirects=True)
    assert "ištrinti negalima" in refused.get_data(as_text=True)
    post(admin, f"/admin/departments/{department.department_id}/delete", {}, token_page="/admin/catalog")
    with Session(get_engine()) as session:
        assert session.get(Department, department.department_id) is None


# ---------- KD 5.6: usage reports ----------

def test_usage_reports_for_admin_and_management(app, users):
    from services.auth import register_user
    admin, v1 = client_for(app, ip="10.0.1.15"), client_for(app, ip="10.0.1.16")
    log_in(admin, users["admin"][1])
    log_in(v1, users["v1"][1])
    before = {d.document_id for d in _my_documents(users["v1"][0])}
    post(v1, "/documents/upload", {"file": docx_file("Kelionės išlaidos iki 100 EUR per dieną.", "keliones.docx")},
         content_type="multipart/form-data")
    doc = next(d for d in _my_documents(users["v1"][0]) if d.document_id not in before)
    post(v1, "/ask", {"question": "Kokios kelionės išlaidos per dieną?", "document_ids": [str(doc.document_id)]},
         token_page="/ask")

    page = get(admin, "/reports").get_data(as_text=True)
    assert "Sistemos naudojimo ataskaita" in page and "Aktyviausi vartotojai" in page
    assert ">keliones<" in page and users["v1"][1] in page
    assert "Kokios kelionės išlaidos" not in page                                      # question texts stay private
    csv_response = get(admin, "/reports.csv")
    assert csv_response.mimetype == "text/csv" and "attachment" in csv_response.headers["Content-Disposition"]
    assert csv_response.get_data(as_text=True).startswith("﻿Laikotarpis;")
    empty = get(admin, "/reports?from=2000-01-01&to=2000-01-02").get_data(as_text=True)
    assert "Per šį laikotarpį klausimų nebuvo" in empty

    email = f"vadovas-{uuid.uuid4().hex[:8]}@test.lt"
    with Session(get_engine()) as session:
        register_user(session, email=email, password=PASSWORD, first_name="V", last_name="Vadovas",
                      department_id=session.scalar(select(Department.department_id).limit(1)), role="management")
    try:
        manager = client_for(app, ip="10.0.1.17")
        log_in(manager, email)
        menu = get(manager, "/documents").get_data(as_text=True)
        assert 'href="/reports"' in menu and "Admin panelė" not in menu
        page = get(manager, "/reports").get_data(as_text=True)
        assert "Žinių bazės naudojimo ataskaita" in page and ">keliones<" in page
        assert "Aktyviausi vartotojai" not in page and users["v1"][1] not in page      # no per-user activity
    finally:
        with Session(get_engine()) as session:
            session.execute(delete(User).where(User.email == email))
            session.commit()
        post(v1, f"/documents/{doc.document_id}/delete", {})


def test_new_pages_are_translated(app, users):
    client = client_for(app, ip="10.0.1.18")
    post(client, "/language", {"lang": "en", "next": "/login"}, token_page="/login")
    log_in(client, users["admin"][1])
    for path in ("/history", "/reports?from=2000-01-01&to=2000-01-02", "/admin/users/new",
                 f"/admin/users/{users['v1'][0]}", "/ask"):
        html = get(client, path).get_data(as_text=True)
        leftover = LT_LETTERS.findall(_visible_text(html))
        assert not leftover, f"Lithuanian text left on {path}: {leftover}"
