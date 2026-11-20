"""Runs QA form E scenarios TS-01 … TS-07 against the running HTTPS site, step by step, and compares every step with
the "Laukiamas rezultatas" column. Use it as a dress rehearsal before the manual run; it does not replace it.

Prerequisites (README): DB and Caddy running, `$env:BEHIND_PROXY="1"; python -m run_web` with the REAL Gemini,
test users from `python -m scripts.make_test_users`, files from `python -m scripts.make_test_files`, and the Caddy
root certificate: `docker cp dms-caddy:/data/caddy/pki/authorities/local/root.crt storage/caddy_root.crt`.

    python -m scripts.qa_acceptance              # all scenarios
    python -m scripts.qa_acceptance TS-01 TS-05  # only these

Two shortcuts, both printed in the output:
- TS-05 step 5: instead of waiting 15 minutes, the lock end time is moved into the past in the database (after the
  script has checked that the lock really lasts 15 minutes).
- TS-06 B (100 users, 5 minutes) is a Locust run (scripts/locustfile.py); this script only reads its last report.
The script cleans up after itself: V1, V2 and U001 lose the documents it uploaded, V1 is unlocked.
The site's login limit is 10 per minute per IP, so the script waits when it hits it (the run takes a few minutes).
"""
import csv
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path

import requests
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from database.engine import get_engine
from database.models import Document, User

BASE = "https://localhost"
CA = "storage/caddy_root.crt"
FILES = Path("samples/test_files")
V1, V2, A1, U001 = "vartotojas1@test.lt", "vartotojas2@test.lt", "admin@test.lt", "user001@test.lt"
PASSWORDS = {V1: "Test1234!", V2: "Test1234!", A1: "Admin1234!", U001: "Test1234!"}

results: list[tuple[str, int, bool, str]] = []
current = ""


def check(step: int, ok: bool, detail: str) -> None:
    results.append((current, step, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {current} po {step} žingsnio: {detail}")


class Browser:
    def __init__(self):
        self.http = requests.Session()
        self.http.verify = CA
        self.http.headers["Referer"] = BASE + "/"       # browsers send it; Flask-WTF checks it on HTTPS

    def get(self, path, **kw):
        return self.http.get(BASE + path, **kw)

    def csrf(self, html: str) -> str:
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def post(self, path, data=None, files=None, page="/documents"):
        token = self.csrf(self.get(page).text)
        return self.http.post(BASE + path, data={**(data or {}), "csrf_token": token}, files=files)

    def login(self, email, password=None):
        while True:
            token = self.csrf(self.get("/login").text)
            r = self.http.post(BASE + "/login", data={"email": email, "password": password or PASSWORDS[email],
                                                     "csrf_token": token})
            if r.status_code != 429:
                return r
            print("    (10 prisijungimų per minutę riba – laukiama 60 s)")
            time.sleep(60)

    def logout(self):
        return self.post("/logout")

    def upload(self, name, summary=False):
        with open(FILES / name, "rb") as handle:
            return self.post("/summaries/upload" if summary else "/documents/upload", files={"file": (name, handle)})

    def doc_id(self, title) -> int | None:
        match = re.search(r'href="/documents/(\d+)">' + re.escape(title) + "<", self.get("/documents").text)
        return int(match.group(1)) if match else None

    def ask(self, question, ids):
        r = self.post("/ask", data={"question": question, "document_ids": [str(i) for i in ids]}, page="/ask")
        html = r.text
        answer = re.search(r'<p class="answer-text">(.*?)</p>', html, re.S)
        sources = re.findall(r'<ul class="sources">(.*?)</ul>', html, re.S)
        return unescape(answer.group(1)).strip() if answer else "", unescape(sources[0]) if sources else ""


def text_of(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", " ", html))


def titles(html: str) -> list[str]:
    return [unescape(t) for t in re.findall(r'href="/documents/\d+">([^<]+)<', html)]


def section(html: str, name: str) -> str:
    """The part of 'Mano dokumentai' under one heading (Dokumentai / Apibendrinimai)."""
    parts = re.split(r'<div class="section-title"><h2>', html)
    return next((p for p in parts if p.startswith(name + "<")), "")


def db():
    return Session(get_engine())


def wipe(email):
    """Remove every document of a test user through the site, so the files and derived rows go too."""
    b = Browser()
    b.login(email)
    for doc in re.findall(r'action="/documents/(\d+)/delete"', b.get("/documents").text):
        b.post(f"/documents/{doc}/delete")
    b.logout()


# ------------------------------------------------------------------ scenarios

def ts01():
    b = Browser()
    b.login(V1)
    r = b.upload("atostogu_tvarka.pdf")
    docs = section(r.text, "Dokumentai")
    check(1, titles(docs) == ["atostogu_tvarka"] and date.today().isoformat() in docs,
          f"sąraše {titles(docs)}, data {'yra' if date.today().isoformat() in docs else 'nėra'}")
    doc = b.doc_id("atostogu_tvarka")
    preview = text_of(b.get(f"/documents/{doc}").text)
    check(2, "Kasmetinės atostogos trunka 20 darbo dienų" in preview, "peržiūroje matomas F1 tekstas")
    r = b.post(f"/documents/{doc}/rename", data={"title": "Atostogų tvarka 2026", "back": "preview"},
               page=f"/documents/{doc}")
    listed = titles(section(b.get("/documents").text, "Dokumentai"))
    check(3, listed == ["Atostogų tvarka 2026"], f"sąraše {listed}")
    r = b.upload("santrauka_2026.pdf", summary=True)
    summaries = titles(section(r.text, "Apibendrinimai"))
    check(4, "išsaugotas" in text_of(r.text) and summaries == ["santrauka_2026"],
          f"pranešimas „…išsaugotas“, skyriuje „Apibendrinimai“: {summaries}")
    b.logout()
    b.login(V1)
    listed = titles(b.get("/documents").text)
    check(5, sorted(listed) == ["Atostogų tvarka 2026", "santrauka_2026"], f"po prisijungimo: {listed}")
    answer, sources = b.ask("Kiek dienų trunka kasmetinės atostogos?", [doc])
    lithuanian = bool(set("ąčęėįšųūž") & set(answer.lower()))
    check(7, "20 darbo dien" in answer and lithuanian, f"„{answer}“ šaltinis: {' '.join(sources.split())}")


def ts02():
    b = Browser()
    b.login(V1)
    doc = b.doc_id("Atostogų tvarka 2026") or b.doc_id("atostogu_tvarka")
    if doc is None:
        b.upload("atostogu_tvarka.pdf")
        doc = b.doc_id("atostogu_tvarka")
    answer, sources = b.ask("Kokia yra įmonės direktoriaus pavardė?", [doc])
    says_missing = any(w in answer.lower() for w in ("nėra", "nerasta", "nepateikta", "neturi"))
    check(4, says_missing and not sources, f"„{answer}“; šaltinių: {'nėra' if not sources else sources}")


def ts03():
    b = Browser()
    b.login(V1)
    b.upload("travel_policy.docx")
    doc = b.doc_id("travel_policy")
    answer, _ = b.ask("What is the daily limit for travel expenses?", [doc])
    english = any(w in f" {answer.lower()} " for w in (" the ", " is ", " per "))
    check(2, "100 EUR" in answer and english and not set("ąčęėįšųūž") & set(answer.lower()), f"„{answer}“")
    answer, _ = b.ask("Per kiek dienų po kelionės reikia pateikti čekius?", [doc])
    check(3, "30 dien" in answer, f"„{answer}“")
    b.post(f"/documents/{doc}/delete")                      # TS-04 expects V1 to have F1 only


def ts04():
    # preconditions: V1 has F1, V2 has F2 (uploaded after V1's)
    wipe(V1), wipe(V2)
    v1, v2 = Browser(), Browser()
    v1.login(V1)
    v1.upload("atostogu_tvarka.pdf")
    v2.login(V2)
    v2.upload("travel_policy.docx")
    v2_doc = v2.doc_id("travel_policy")
    v1.logout(), v2.logout()

    a = Browser()
    a.login(A1)
    page = a.get("/admin")
    emails = set(re.findall(r"[\w.]+@test\.lt", page.text))
    check(2, {V1, V2, A1} <= emails,
          f"matomos {V1}, {V2}, {A1} (iš viso paskyrų sąraše: {len(emails)})")
    v1_list, v2_list = ([unescape(t).strip() for t in
                         re.findall(r'<td class="title">([^<]+)<', a.get(_admin_link(page.text, email)).text)]
                        for email in (V1, V2))
    check(3, v1_list in (["atostogu_tvarka"], ["Atostogų tvarka 2026"]) and v2_list == ["travel_policy"],
          f"V1: {v1_list}, V2: {v2_list}")
    a.logout()

    v1 = Browser()
    v1.login(V1)
    menu = v1.get("/documents").text
    check(5, "Admin panelė" not in menu, "meniu nuorodos „Admin panelė“ nėra")
    r = v1.get("/admin")
    check(6, r.status_code == 403 and "Prieiga draudžiama" in r.text and V2 not in r.text,
          f"HTTP {r.status_code}, „Prieiga draudžiama“, vartotojų sąrašo nematyti")
    listed = titles(menu)
    check(7, "travel_policy" not in listed and len(listed) == 1, f"V1 sąraše: {listed}")
    r = v1.get(f"/documents/{v2_doc}")
    check(8, r.status_code == 404 and "Employees may claim" not in r.text, f"/documents/{v2_doc} → HTTP {r.status_code}")


def _admin_link(html, email):
    row = re.search(r'<td class="title">' + re.escape(email) + r"</td>.*?href=\"(/admin/users/\d+/documents)\"",
                    html, re.S)
    return row.group(1)


def ts05():
    with db() as s:
        hashes = dict(s.execute(select(User.email, User.password_hash).where(User.email.in_([V1, V2, A1]))).all())
        s.execute(update(User).where(User.email == V1).values(failed_attempts=0, locked_until=None))
        s.commit()
    ok = all(h.startswith("$2b$") and 59 <= len(h) <= 61 and "1234!" not in h for h in hashes.values())
    check(1, ok and len(hashes) == 3, ", ".join(f"{e}: {h[:7]}… ({len(h)} simb.)" for e, h in hashes.items()))

    b = Browser()
    for _ in range(4):
        r = b.login(V1, "Klaida111")
    check(2, "Neteisingas slaptažodis" in text_of(r.text) and "užblokuota" not in text_of(r.text),
          " ".join(re.findall(r"Neteisingas[^.]*\.", text_of(r.text))[:1]))
    r = b.login(V1, "Klaida111")
    message = " ".join(re.findall(r"Paskyra užblokuota[^<.]*", text_of(r.text))[:1])
    check(3, "užblokuota 15 minučių" in message, message or "pranešimo apie užblokavimą nėra")
    r = b.login(V1)
    with db() as s:
        locked_until = s.scalar(select(User.locked_until).where(User.email == V1))
    minutes = (locked_until - datetime.now(timezone.utc)).total_seconds() / 60 if locked_until else 0
    check(4, "užblokuota" in text_of(r.text) and "/login" in r.url,
          f"teisingas slaptažodis atmestas; DB užrakinta dar {minutes:.1f} min.")
    with db() as s:   # shortcut for "wait 15 minutes"
        s.execute(update(User).where(User.email == V1).values(locked_until=datetime.now(timezone.utc) - timedelta(seconds=1)))
        s.commit()
    r = b.login(V1)
    check(5, r.url.endswith("/documents"), "(15 min. laukimas imituotas DB) prisijungta")

    r = requests.get("http://localhost/", allow_redirects=False)
    check(6, r.status_code in (301, 302, 307, 308) and r.headers.get("Location", "").startswith("https://"),
          f"http:// → HTTP {r.status_code} → {r.headers.get('Location')}")
    v2 = Browser()
    v2.login(V2)
    html = v2.get("/ask").text
    insecure = re.findall(r'(?:src|href|action)="http://[^"]+"', html)
    hsts = v2.get("/ask").headers.get("Strict-Transport-Security")
    check(7, not insecure, f"puslapyje http:// nuorodų: {len(insecure)} (HSTS: {hsts or 'nėra'})")

    root = Path(".")
    apps = [p for p in root.rglob("*") if p.suffix.lower() in (".apk", ".aab", ".ipa") and ".venv" not in p.parts]
    readme = Path("README.md").read_text(encoding="utf-8").lower()
    mobile = [w for w in ("google play", "app store", ".apk", "mobiliosios programėlės diegimas") if w in readme]
    check(8, not apps and not mobile, f".apk/.aab/.ipa: {len(apps)}; README mobiliosios instrukcijos: {mobile or 'nėra'}")


def ts06():
    from scripts.make_test_files import F4
    b = Browser()
    b.login(V1)
    ids = {}
    for name, *_ in F4:
        b.upload(name)
        ids[name] = b.doc_id(name.removesuffix(".pdf"))
    times, right = [], 0
    for name, _title, _fact, page, question, expected in F4:
        started = time.perf_counter()
        answer, sources = b.ask(question, list(ids.values()))
        times.append(time.perf_counter() - started)
        right += any(e.lower() in answer.lower() for e in expected) and f"{name.removesuffix('.pdf')}" in sources \
            and f"p. {page}" in " ".join(sources.split())
    check(3, len(times) == 10 and max(times) <= 30 and right >= 9,
          f"10 laikų, ilgiausias {max(times):.1f} s, vidurkis {sum(times) / len(times):.1f} s; "
          f"teisingi su teisingu šaltiniu: {right}/10 (FR-02 ≥ 9)")
    for doc in ids.values():
        b.post(f"/documents/{doc}/delete")

    stats = Path("storage/locust_stats.csv")
    if not stats.exists():
        check(6, False, "Locust ataskaitos nėra (paleiskite scripts/locustfile.py)")
        return
    rows = {r["Name"]: r for r in csv.DictReader(stats.open(encoding="utf-8"))}
    total = rows["Aggregated"]
    when = datetime.fromtimestamp(stats.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    logins = int(rows.get("POST /login", {}).get("Request Count", 0))
    check(6, int(total["Failure Count"]) == 0 and float(total["Max Response Time"]) <= 60_000 and logins >= 100,
          f"Locust ({when}, imituotas DI pagal D3): {logins} vartotojų, {total['Request Count']} užklausų, "
          f"nutrūkusių {total['Failure Count']}, ilgiausia {float(total['Max Response Time']) / 1000:.1f} s")


def ts07():
    b = Browser()
    b.login(V1)
    doc = b.doc_id("Atostogų tvarka 2026")
    if doc is None:                                     # precondition from TS-01
        b.upload("atostogu_tvarka.pdf")
        doc = b.doc_id("atostogu_tvarka")
        b.post(f"/documents/{doc}/rename", data={"title": "Atostogų tvarka 2026"})
        b.ask("Kiek dienų trunka kasmetinės atostogos?", [doc])
    with db() as s:
        file_path = s.scalar(select(Document.file_path).where(Document.document_id == doc))
    r = b.post(f"/documents/{doc}/delete")
    check(2, "Dokumentas ir visi jo duomenys ištrinti." in text_of(r.text)
          and "Atostogų tvarka 2026" not in titles(r.text), "pranešimas rodomas, sąraše nebėra")
    check(3, "Atostogų tvarka 2026" not in b.get("/ask").text, "„Klausimai“ sąraše nebėra")
    with db() as s:
        chunks = s.scalar(text("SELECT count(*) FROM chunks WHERE document_id = :d"), {"d": doc})
        sources = s.scalar(text("SELECT count(*) FROM sources WHERE document_id = :d"), {"d": doc})
    check(4, chunks == 0 and sources == 0, f"chunks: {chunks}, sources: {sources}")
    check(5, not Path(file_path).exists(), f"{file_path} {'yra' if Path(file_path).exists() else 'nerastas'}")
    r = b.get(f"/documents/{doc}")
    check(6, r.status_code == 404 and "Nerasta" in r.text, f"HTTP {r.status_code}")

    import subprocess
    run = lambda *a: subprocess.run([sys.executable, "-m", "scripts.fill_documents", U001, *a],
                                    capture_output=True, text=True, encoding="utf-8")
    wipe(U001)
    run("999")
    u = Browser()
    u.login(U001)
    r = u.upload("atostogu_tvarka.pdf")
    check(8, "įkeltas ir apdorotas" in text_of(r.text), " ".join(re.findall(r"„[^“]+“ įkeltas[^<]*", text_of(r.text))[:1]))
    r = u.upload("travel_policy.docx")
    check(9, "Galima saugoti ne daugiau kaip 1000 dokumentų." in text_of(r.text)
          and "travel_policy" not in titles(u.get("/documents").text), "1001-asis atmestas, F2 sąraše nėra")
    run("--remove")
    wipe(U001)


SCENARIOS = {"TS-01": ts01, "TS-02": ts02, "TS-03": ts03, "TS-04": ts04, "TS-05": ts05, "TS-06": ts06, "TS-07": ts07}


def main() -> None:
    global current
    chosen = [a.upper() for a in sys.argv[1:]] or list(SCENARIOS)
    for email in (V1, V2):                              # TS-01 precondition: empty list
        wipe(email)
    try:
        for name in chosen:
            current = name
            print(f"\n{name}")
            try:
                SCENARIOS[name]()
            except Exception as exc:                    # a crash fails the scenario, the others still run
                check(0, False, f"klaida: {exc!r}")
    finally:
        with db() as s:
            s.execute(update(User).where(User.email == V1).values(failed_attempts=0, locked_until=None))
            s.commit()
        for email in (V1, V2):
            wipe(email)
    print("\nSuvestinė")
    for name in chosen:
        steps = [r for r in results if r[0] == name]
        print(f"  {name}: {'ATITIKO' if steps and all(r[2] for r in steps) else 'NEATITIKO'}"
              f" ({sum(r[2] for r in steps)}/{len(steps)} patikrų)")
    sys.exit(0 if all(r[2] for r in results) else 1)


if __name__ == "__main__":
    main()
