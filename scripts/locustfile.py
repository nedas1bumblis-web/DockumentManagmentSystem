"""TS-06 load test: 100 users (user001..user100 from scripts.make_test_users) log in, upload, ask questions.

Run the server with the mock AI (plan, section 5, P1: the Gemini quota would fail the test, not your system):
    $env:BEHIND_PROXY="1"; $env:USE_MOCK_AI="1"; $env:LOGIN_RATE_LIMIT="10000 per minute"; python -m run_web
Then, headless, 100 users, 10 new per second, 3 minutes:
    locust -f scripts/locustfile.py --host https://localhost -u 100 -r 10 -t 3m --headless --csv storage/locust
"""
import io
import itertools
import re
import threading

import urllib3
from docx import Document as new_docx
from locust import HttpUser, between, task

urllib3.disable_warnings()                    # Caddy's local certificate is not in the system trust store
_numbers = itertools.count(1)
_lock = threading.Lock()
_TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')
QUESTIONS = ["Kiek dienų trunka kasmetinės atostogos?", "How many days of annual leave do employees get?",
             "Kas tvirtina komandiruotes?", "What is the daily travel allowance?"]


def _docx(number: int) -> bytes:
    doc = new_docx()
    doc.add_paragraph(f"Darbuotojo {number} atmintinė. Kasmetinės atostogos trunka 28 kalendorines dienas.")
    doc.add_paragraph("Komandiruotes tvirtina skyriaus vadovas. Dienpinigiai užsienyje – 100 EUR per dieną.")
    doc.add_paragraph("Employees get 28 calendar days of annual leave. The daily travel allowance is 100 EUR.")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


class Employee(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        with _lock:
            self.number = (next(_numbers) - 1) % 100 + 1
        self.client.verify = False
        self.client.headers["Referer"] = self.host + "/"
        page = self.client.get("/login", name="GET /login").text
        response = self.client.post("/login", name="POST /login", allow_redirects=False, data={
            "csrf_token": _TOKEN.search(page).group(1),
            "email": f"user{self.number:03d}@test.lt", "password": "Test1234!"})
        if response.status_code != 302:
            raise RuntimeError(f"login failed for user{self.number:03d}: {response.status_code}")
        self.token = _TOKEN.search(self.client.get("/documents", name="GET /documents").text).group(1)
        self.client.post("/documents/upload", name="POST /documents/upload", data={"csrf_token": self.token},
                         files={"file": (f"atmintine{self.number}.docx", _docx(self.number))})
        ask_page = self.client.get("/ask", name="GET /ask").text
        self.document_ids = re.findall(r'name="document_ids" value="(\d+)"', ask_page)
        self.questions = itertools.cycle(QUESTIONS)

    @task(3)
    def ask(self):
        with self.client.post("/ask", name="POST /ask", catch_response=True, data={
                "csrf_token": self.token, "question": next(self.questions), "document_ids": self.document_ids}) as r:
            if r.status_code != 200 or "Atsakymas" not in r.text:
                r.failure(f"no answer (HTTP {r.status_code})")
            elif r.elapsed.total_seconds() > 30:                          # NFR-02: answer within 30 s
                r.failure(f"answer took {r.elapsed.total_seconds():.1f} s")

    @task(1)
    def browse(self):
        self.client.get("/documents", name="GET /documents")

    def on_stop(self):
        for document_id in self.document_ids:
            self.client.post(f"/documents/{document_id}/delete", name="POST /documents/[id]/delete",
                             data={"csrf_token": self.token})
