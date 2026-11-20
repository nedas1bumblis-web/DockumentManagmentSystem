"""Flask web layer (decision D6). Routes follow the table in phase 7 of the implementation plan."""
import logging
import os
from datetime import timedelta

from flask import Flask, g, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFError, CSRFProtect

from app_config import MAX_UPLOAD_BYTES

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://", headers_enabled=True)
log = logging.getLogger(__name__)

CSP = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    secret = os.getenv("FLASK_SECRET_KEY")
    app.config.update(
        SECRET_KEY=secret,
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "1") == "1",   # browsers still accept it on http://127.0.0.1
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES + 1024 * 1024,              # rejected before our code reads the body
        LOGIN_RATE_LIMIT=os.getenv("LOGIN_RATE_LIMIT", "10 per minute"),
        WTF_CSRF_TIME_LIMIT=None,                                        # the token lives as long as the session
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("FLASK_SECRET_KEY is missing from .env")

    # Behind Caddy, run_web.py tells waitress to trust X-Forwarded-For/Proto (see BEHIND_PROXY there),
    # so request.remote_addr is the browser's IP (per-IP login limit) and request.is_secure is true.

    csrf.init_app(app)
    limiter.init_app(app)

    from web import views
    app.register_blueprint(views.bp)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"          # site isolation (ZAP 90004)
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def error_page(code: int, title: str, message: str):
        from web.i18n import gettext as _
        return render_template("error.html", code=code, title=_(title), message=_(message)), code

    @app.errorhandler(403)
    def forbidden(_):
        return error_page(403, "Prieiga draudžiama", "Neturite teisės matyti šio puslapio.")

    @app.errorhandler(404)
    def not_found(_):
        return error_page(404, "Nerasta", "Puslapis arba dokumentas nerastas.")

    @app.errorhandler(413)
    def too_large(_):
        return error_page(413, "Failas per didelis", f"Didžiausias leidžiamas dydis: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    @app.errorhandler(429)
    def too_many(_):
        return error_page(429, "Per daug bandymų", "Palaukite minutę ir bandykite dar kartą.")

    @app.errorhandler(CSRFError)
    def bad_csrf(_):
        return error_page(400, "Sesija pasibaigė", "Atnaujinkite puslapį ir bandykite dar kartą.")

    @app.errorhandler(500)
    def server_error(_):                            # the traceback goes to the server log, never to the browser
        return error_page(500, "Įvyko klaida", "Bandykite dar kartą vėliau.")

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    return app
