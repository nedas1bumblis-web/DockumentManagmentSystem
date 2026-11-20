"""Administration (KD process 5.5 and the TOP DFD flow "vartotojų ir kategorijų duomenys"):
user accounts and their rights, document categories and departments.

Every message raised as AdminError is safe to show to the administrator.
"""
import re

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import Category, Department, Document, User
from security import PasswordError, hash_password
from services.auth import EmailTaken, register_user

ROLES = ("employee", "admin", "management")       # KD: darbuotojas, administratorius, bendro valdymo skyrius
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AdminError(ValueError):
    """The change is not allowed; the message is safe to show."""


def _clean(value: str | None, limit: int, what: str, required: bool = True) -> str | None:
    value = (value or "").strip()
    if not value:
        if required:
            raise AdminError(f"Laukas „{what}“ privalomas.")
        return None
    if len(value) > limit:
        raise AdminError(f"Laukas „{what}“ ilgesnis nei {limit} simbolių.")
    return value


def _department(session: Session, department_id) -> int:
    try:
        department_id = int(department_id)
    except (TypeError, ValueError):
        raise AdminError("Pasirinkite padalinį.") from None
    if session.get(Department, department_id) is None:
        raise AdminError("Pasirinkite padalinį.")
    return department_id


def _role(role: str) -> str:
    if role not in ROLES:
        raise AdminError("Neteisinga rolė.")
    return role


# ---------- users ----------

def create_user(session: Session, *, email: str, password: str, first_name: str, last_name: str,
                department_id, role: str) -> User:
    email = _clean(email, 100, "El. paštas").lower()
    if not _EMAIL.match(email):
        raise AdminError("Neteisingas el. pašto adresas.")
    first_name = _clean(first_name, 50, "Vardas")
    last_name = _clean(last_name, 50, "Pavardė")
    department_id, role = _department(session, department_id), _role(role)
    try:
        return register_user(session, email=email, password=password, first_name=first_name, last_name=last_name,
                             department_id=department_id, role=role)
    except PasswordError as exc:
        raise AdminError(str(exc)) from None
    except EmailTaken:
        raise AdminError("Vartotojas su tokiu el. paštu jau yra.") from None


def update_user(session: Session, admin: User, user_id: int, *, first_name: str, last_name: str, department_id,
                role: str, is_active: bool) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise LookupError(user_id)
    role = _role(role)
    if user.user_id == admin.user_id and (role != "admin" or not is_active):
        raise AdminError("Negalite atimti administratoriaus teisių ar išjungti savo paskyros.")
    user.first_name = _clean(first_name, 50, "Vardas")
    user.last_name = _clean(last_name, 50, "Pavardė")
    user.department_id = _department(session, department_id)
    user.role, user.is_active = role, is_active
    session.commit()
    return user


def unlock_user(session: Session, user_id: int) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise LookupError(user_id)
    user.locked_until, user.failed_attempts = None, 0
    session.commit()


def set_password(session: Session, user_id: int, password: str) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise LookupError(user_id)
    try:
        user.password_hash = hash_password(password)
    except PasswordError as exc:
        raise AdminError(str(exc)) from None
    user.locked_until, user.failed_attempts = None, 0
    session.commit()


# ---------- categories and departments ----------

def default_category_id(session: Session) -> int:
    """The first category ("Nekategorizuota" after init_db) is the default and cannot be deleted."""
    return session.scalar(select(Category.category_id).order_by(Category.category_id).limit(1))


def catalog(session: Session) -> dict:
    """Categories and departments with how often each is used."""
    docs_per_category = dict(session.execute(select(Document.category_id, func.count()).group_by(Document.category_id)).all())
    docs_per_department = dict(session.execute(select(Document.department_id, func.count())
                                               .group_by(Document.department_id)).all())
    users_per_department = dict(session.execute(select(User.department_id, func.count())
                                                .group_by(User.department_id)).all())
    categories = session.scalars(select(Category).order_by(Category.category_id)).all()
    departments = session.scalars(select(Department).order_by(Department.department_id)).all()
    return {
        "categories": [(c, docs_per_category.get(c.category_id, 0)) for c in categories],
        "departments": [(d, users_per_department.get(d.department_id, 0), docs_per_department.get(d.department_id, 0))
                        for d in departments],
        "default_category_id": categories[0].category_id if categories else None,
    }


def save_category(session: Session, category_id: int | None, name: str, description: str | None) -> Category:
    category = Category() if category_id is None else session.get(Category, category_id)
    if category is None:
        raise LookupError(category_id)
    category.name = _clean(name, 100, "Pavadinimas")
    category.description = _clean(description, 255, "Aprašymas", required=False)
    session.add(category)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise AdminError("Kategorija tokiu pavadinimu jau yra.") from None
    return category


def delete_category(session: Session, category_id: int) -> None:
    category = session.get(Category, category_id)
    if category is None:
        raise LookupError(category_id)
    if category_id == default_category_id(session):
        raise AdminError("Numatytosios kategorijos ištrinti negalima.")
    if session.scalar(select(func.count()).select_from(Document).where(Document.category_id == category_id)):
        raise AdminError("Kategorijos, kuriai priskirta dokumentų, ištrinti negalima.")
    session.delete(category)
    session.commit()


def save_department(session: Session, department_id: int | None, name: str, code: str,
                    description: str | None) -> Department:
    department = Department() if department_id is None else session.get(Department, department_id)
    if department is None:
        raise LookupError(department_id)
    department.name = _clean(name, 100, "Pavadinimas")
    department.code = _clean(code, 20, "Kodas").upper()
    department.description = _clean(description, 255, "Aprašymas", required=False)
    session.add(department)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise AdminError("Padalinys tokiu kodu jau yra.") from None
    return department


def delete_department(session: Session, department_id: int) -> None:
    department = session.get(Department, department_id)
    if department is None:
        raise LookupError(department_id)
    used = (session.scalar(select(func.count()).select_from(User).where(User.department_id == department_id)) or
            session.scalar(select(func.count()).select_from(Document).where(Document.department_id == department_id)))
    if used:
        raise AdminError("Padalinio, kuriame yra vartotojų ar dokumentų, ištrinti negalima.")
    session.delete(department)
    session.commit()
