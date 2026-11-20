"""Start the web app with waitress (a production WSGI server that runs on Windows).

    python -m run_web                 -> http://127.0.0.1:8000 (behind Caddy for HTTPS, see Caddyfile)
"""
import logging
import os

from waitress import serve

from web import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    host = os.getenv("WEB_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_PORT", "8000"))
    print(f"Serving on http://{host}:{port}")
    proxy = {}
    if os.getenv("BEHIND_PROXY", "0") == "1":
        # Caddy sets X-Forwarded-*; waitress drops them unless told to trust the proxy. Safe only because the
        # server listens on 127.0.0.1, so nothing but the local proxy can reach it.
        proxy = dict(trusted_proxy="*", trusted_proxy_count=1,
                     trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"})
    serve(create_app(), host=host, port=port, threads=int(os.getenv("WEB_THREADS", "16")), **proxy)
