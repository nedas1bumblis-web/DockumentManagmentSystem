"""Print the PostgreSQL DDL that init_db creates, straight from database/models.py (KD appendix 2).

    python -m scripts.print_schema_sql > storage/schema.sql
"""
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from database.models import Base


def schema_sql() -> str:
    dialect = postgresql.dialect()
    parts = ["-- DBVS: PostgreSQL 16 + pgvector; sugeneruota iš database/models.py (SQLAlchemy)",
             "CREATE EXTENSION IF NOT EXISTS vector;"]
    for table in Base.metadata.sorted_tables:
        parts.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in sorted(table.indexes, key=lambda i: i.name):
            parts.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
    return "\n\n".join(parts) + "\n"


if __name__ == "__main__":
    print(schema_sql(), end="")
