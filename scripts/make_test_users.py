"""Creates the QA test accounts from form E: V1, V2, A1 and U001-U100. Safe to run twice.

    python -m scripts.make_test_users                    # the QA accounts only (TS-04 counts on them)
    python -m scripts.make_test_users --with-management  # also vadovas@test.lt / Vadovas1234! (KD 5.6 reports)
"""
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.engine import get_engine
from database.models import Department
from services.auth import EmailTaken, register_user


def main() -> None:
    accounts = [("vartotojas1@test.lt", "Test1234!", "employee"),
                ("vartotojas2@test.lt", "Test1234!", "employee"),
                ("admin@test.lt", "Admin1234!", "admin")]
    accounts += [(f"user{n:03d}@test.lt", "Test1234!", "employee") for n in range(1, 101)]
    if "--with-management" in sys.argv:
        accounts.append(("vadovas@test.lt", "Vadovas1234!", "management"))
    created = 0
    with Session(get_engine()) as session:
        department_id = session.scalar(select(Department.department_id).limit(1))
        for email, password, role in accounts:
            try:
                register_user(session, email=email, password=password, first_name="Test",
                              last_name=email.split("@")[0], department_id=department_id, role=role)
                created += 1
            except EmailTaken:
                pass
    print(f"created {created}, already existed {len(accounts) - created}")


if __name__ == "__main__":
    main()
