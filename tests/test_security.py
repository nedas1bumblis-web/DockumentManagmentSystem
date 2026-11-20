from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import bcrypt
import pytest

from security import (LOCK_MINUTES, PasswordError, check_login, hash_password, validate_password, verify_password)

REAL_BCRYPT = not getattr(bcrypt, "IS_FAKE", False)

T0 = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def make_user(password="Test1234!", active=True):
    return SimpleNamespace(password_hash=hash_password(password), is_active=active, failed_attempts=0, locked_until=None)


def test_hash_verify_roundtrip():
    hashed = hash_password("Test1234!")
    assert verify_password("Test1234!", hashed) and not verify_password("Test1235!", hashed)


@pytest.mark.skipif(not REAL_BCRYPT, reason="needs the real bcrypt library")
def test_real_bcrypt_hash_format_for_TS05():
    hashed = hash_password("Test1234!")
    assert hashed.startswith("$2b$") and len(hashed) == 60 and "Test1234!" not in hashed


def test_password_rules():
    for bad in ("short", "x" * 73, "ą" * 40):              # too short / too long / 80 bytes
        with pytest.raises(PasswordError):
            validate_password(bad)
    validate_password("Admin1234!")
    assert verify_password("x" * 73, hash_password("Test1234!")) is False      # no exception, just 'no'


def test_ts05_lockout_sequence():
    user = make_user()
    for _ in range(4):
        assert check_login(user, "Klaida111", T0) == "bad_credentials"     # 4 mistakes: not locked yet
    assert check_login(user, "Klaida111", T0) == "locked"                  # 5th mistake locks
    assert check_login(user, "Test1234!", T0 + timedelta(minutes=1)) == "locked"   # right password still refused
    assert check_login(user, "Test1234!", T0 + timedelta(minutes=LOCK_MINUTES - 1)) == "locked"
    assert check_login(user, "Test1234!", T0 + timedelta(minutes=LOCK_MINUTES, seconds=1)) == "ok"
    assert user.failed_attempts == 0 and user.locked_until is None


def test_failed_attempts_start_again_after_lock_expires():
    user = make_user()
    for _ in range(5):
        check_login(user, "bad-password", T0)
    later = T0 + timedelta(minutes=LOCK_MINUTES + 1)
    assert check_login(user, "bad-password", later) == "bad_credentials"
    assert user.failed_attempts == 1


def test_success_resets_the_counter():
    user = make_user()
    for _ in range(4):
        check_login(user, "bad-password", T0)
    assert check_login(user, "Test1234!", T0) == "ok" and user.failed_attempts == 0


def test_requests_while_locked_do_not_extend_the_lock():
    user = make_user()
    for _ in range(5):
        check_login(user, "bad-password", T0)
    first_deadline = user.locked_until
    check_login(user, "bad-password", T0 + timedelta(minutes=5))
    assert user.locked_until == first_deadline


def test_unknown_user_and_inactive_user():
    assert check_login(None, "whatever123", T0) == "bad_credentials"
    assert check_login(make_user(active=False), "Test1234!", T0) == "inactive"
    assert check_login(make_user(active=False), "wrong-password", T0) == "bad_credentials"   # no hint it exists
