import random
import time

RETRYABLE_CODES = {429, 500, 502, 503, 504}       # rate limit and temporary server errors
_client = None


def get_client():
    global _client
    if _client is None:
        from google import genai                  # imported lazily so mock mode needs no Gemini library
        _client = genai.Client()                  # reads GEMINI_API_KEY from the environment
    return _client


def with_retries(call, attempts: int = 5, base_delay: float = 1.0, sleep=time.sleep):
    """Run call(); on 429/5xx wait 1 s, 2 s, 4 s ... (plus jitter) and try again."""
    for attempt in range(attempts):
        try:
            return call()
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code not in RETRYABLE_CODES or attempt == attempts - 1:
                raise
            sleep(base_delay * 2 ** attempt + random.random())
