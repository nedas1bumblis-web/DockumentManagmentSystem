import sys

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database.engine import get_engine
from database.models import Base, Category, Department

# KD 1.1 and 8 lentelė: the company's departments and the document categories named there. The first row of each
# is the default (an upload without a chosen category lands in "Nekategorizuota").
DEPARTMENTS = [("Bendras", "GEN"), ("Bendro valdymo skyrius", "BVS"), ("Personalo skyrius", "PER"),
               ("Finansų skyrius", "FIN"), ("Marketingo (prekybos) skyrius", "MKT"),
               ("Žinių (dokumentų) valdymo skyrius", "ZDV")]
CATEGORIES = ["Nekategorizuota", "Instrukcijos", "Sutartys", "Ataskaitos", "Techniniai aprašymai"]


def init_db(reset: bool = False) -> None:
    engine = get_engine()
    with engine.begin() as connection:                       # needed once per database, before the vector column
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    if reset:
        Base.metadata.drop_all(engine)                       # DEV ONLY: deletes every table of the models below
    Base.metadata.create_all(engine)                         # never alters existing tables
    with Session(engine) as session:                         # the KD makes department and category mandatory
        seed_catalog(session)


def seed_catalog(session: Session) -> None:
    """Adds the KD departments and categories that are missing; never changes or removes existing rows."""
    codes = set(session.scalars(select(Department.code)))
    session.add_all(Department(name=name, code=code) for name, code in DEPARTMENTS if code not in codes)
    session.flush()
    names = set(session.scalars(select(Category.name)))
    session.add_all(Category(name=name) for name in CATEGORIES if name not in names)
    session.commit()


if __name__ == "__main__":
    wants_reset = "--reset" in sys.argv
    if wants_reset and input("This DELETES all tables and data. Type YES to continue: ") != "YES":
        sys.exit("Cancelled.")
    init_db(reset=wants_reset)
    print("Database ready.")
