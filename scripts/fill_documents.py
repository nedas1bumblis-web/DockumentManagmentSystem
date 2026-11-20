"""TS-07 helper: give a user N placeholder documents so the 1000-document limit (FR-08) can be tested in the UI.

    python -m scripts.fill_documents user001@test.lt 999       # adds 999 placeholders ("riba-001" ...)
    python -m scripts.fill_documents user001@test.lt --remove  # deletes them again (real uploads stay)

Placeholders have no file and no chunks; they only count towards the limit.
"""
import sys

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from database.engine import get_engine
from database.models import Category, Document, User

PREFIX = "riba-"


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    email, arg = sys.argv[1].strip().lower(), sys.argv[2]
    with Session(get_engine()) as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            sys.exit(f"No user {email}")
        if arg == "--remove":
            result = session.execute(delete(Document).where(Document.author_id == user.user_id,
                                                            Document.title.startswith(PREFIX),
                                                            Document.file_path == ""))
            session.commit()
            print(f"removed {result.rowcount} placeholders")
            return
        category_id = session.scalar(select(Category.category_id).limit(1))
        session.add_all(Document(author_id=user.user_id, department_id=user.department_id, category_id=category_id,
                                 title=f"{PREFIX}{n:04d}", file_type="pdf", file_path="", status="ready")
                        for n in range(1, int(arg) + 1))
        session.commit()
        print(f"added {arg} placeholders to {email}")


if __name__ == "__main__":
    main()
