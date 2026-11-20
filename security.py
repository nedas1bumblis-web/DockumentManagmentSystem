"""Passwords (bcrypt, NFR-01) and the 5-failures / 15-minutes lockout."""
from datetime import datetime, timedelta, timezone

import bcrypt

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
MIN_PASSWORD_CHARS = 8
MAX_PASSWORD_BYTES = 72        # bcrypt ignores (old versions) or rejects (bcrypt >= 5.0) anything longer


class PasswordError(ValueError):
    """Password does not meet the rules; the message is safe to show to the user."""


def validate_password(plain: str) -> None:
    if len(plain) < MIN_PASSWORD_CHARS:
        raise PasswordError(f"Slaptažodis turi būti ne trumpesnis nei {MIN_PASSWORD_CHARS} simboliai.")
    if len(plain.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise PasswordError(f"Slaptažodis per ilgas (daugiausia {MAX_PASSWORD_BYTES} baitai).")


def hash_password(plain: str) -> str:
    validate_password(plain)
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    data = plain.encode("utf-8")
    if len(data) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(data, hashed.encode("ascii"))
    except ValueError:                        # malformed hash in the database
        return False


_dummy_hash: str | None = None


def check_login(user, password: str, now: datetime | None = None) -> str:
    """user: a User row or None. Returns 'ok' | 'locked' | 'bad_credentials' | 'inactive'.

    Changes user.failed_attempts / user.locked_until; the caller commits.
    The caller should load the row with SELECT ... FOR UPDATE, otherwise parallel requests can skip the counter.
    """
    global _dummy_hash
    now = now or datetime.now(timezone.utc)
    if user is None:                          # unknown e-mail: spend the same time, give the same answer
        _dummy_hash = _dummy_hash or hash_password("dummy-password-1")
        verify_password(password, _dummy_hash)
        return "bad_credentials"
    if user.locked_until is not None:
        if user.locked_until > now:
            return "locked"                   # even the right password is refused while locked (TS-05 step 4)
        user.locked_until, user.failed_attempts = None, 0
    if verify_password(password, user.password_hash):
        if not user.is_active:
            return "inactive"
        user.failed_attempts = 0
        return "ok"
    user.failed_attempts += 1
    if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        return "locked"
    return "bad_credentials"
