"""Lets the pure-logic tests run on a machine where bcrypt / google-genai are not installed.

On your own machine the real libraries are used, so nothing here is faked.
"""
import sys
import types

try:
    import bcrypt  # noqa: F401
except ModuleNotFoundError:
    fake = types.ModuleType("bcrypt")
    fake.IS_FAKE = True
    fake.gensalt = lambda rounds=12: b"$2b$12$" + b"s" * 22

    def _hashpw(password: bytes, salt: bytes) -> bytes:
        if len(password) > 72:                   # bcrypt >= 5.0 raises here
            raise ValueError("password cannot be longer than 72 bytes")
        return b"$2b$12$" + salt[-22:] + password[::-1]

    fake.hashpw = _hashpw
    fake.checkpw = lambda password, hashed: hashed == _hashpw(password, hashed[7:29])
    sys.modules["bcrypt"] = fake
