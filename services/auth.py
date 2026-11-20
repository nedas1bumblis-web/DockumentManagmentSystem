from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import User
from security import check_login, hash_password


class EmailTaken(Exception):
    pass


def register_user(session: Session, *, email: str, password: str, first_name: str, last_name: str,
                  department_id: int, role: str = "employee") -> User:
    user = User(email=email.strip().lower(), password_hash=hash_password(password), first_name=first_name.strip(),
                last_name=last_name.strip(), department_id=department_id, role=role)
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:                  # the UNIQUE constraint decides, not a racy "SELECT first"
        session.rollback()
        raise EmailTaken(email) from exc
    return user


def login(session: Session, email: str, password: str) -> tuple[str, User | None]:
    """Returns ('ok' | 'locked' | 'bad_credentials' | 'inactive', user-or-None)."""
    user = session.scalar(select(User).where(User.email == email.strip().lower()).with_for_update())
    status = check_login(user, password)
    session.commit()                               # also on failure: the counter must be saved, and the row unlocked
    return status, (user if status == "ok" else None)
