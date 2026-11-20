from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, func, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app_config import EMBEDDING_DIM


class Base(DeclarativeBase):
    pass


class Department(Base):                       # KD: padalinys
    __tablename__ = "departments"
    department_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))


class Category(Base):                         # KD: kategorija
    __tablename__ = "categories"
    category_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))


class User(Base):                             # KD: vartotojas
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('employee', 'admin', 'management')", name="ck_users_role"),)
    user_id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.department_id"))
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="employee", server_default="employee")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))   # NFR-01
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))               # NFR-01
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):                         # KD: dokumentas
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("file_type IN ('pdf', 'docx')", name="ck_documents_file_type"),
        CheckConstraint("kind IN ('document', 'summary')", name="ck_documents_kind"),
        CheckConstraint("status IN ('processing', 'ready', 'failed')", name="ck_documents_status"),
    )
    document_id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.category_id"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.department_id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    file_type: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(10), default="document", server_default="document")   # FR-05: 'summary'
    file_path: Mapped[str] = mapped_column(String(255))
    page_count: Mapped[int | None]
    document_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="processing", server_default="processing")
    error_message: Mapped[str | None] = mapped_column(Text)


class Chunk(Base):                            # not in the KD yet: the pieces that RAG searches
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),)  # also indexes document_id
    chunk_id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.document_id", ondelete="CASCADE"))
    chunk_index: Mapped[int]
    page: Mapped[int | None]
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=False)


class UserQuery(Base):                        # KD: uzklausa
    __tablename__ = "queries"
    query_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Answer(Base):                           # KD: atsakymas
    __tablename__ = "answers"
    answer_id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("queries.query_id", ondelete="CASCADE"), index=True)
    answer_text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))   # best retrieval similarity in %, not "truth"
    model_name: Mapped[str | None] = mapped_column(String(60))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Source(Base):                           # KD: saltinis
    __tablename__ = "sources"
    source_id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.answer_id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.document_id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int | None]           # DOCX has no real pages: see decision D3
