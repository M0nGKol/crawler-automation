from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, func
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship, sessionmaker

DATABASE_URL = "sqlite:///./crawler.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    company: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="admin", nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    google_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    sheet_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sites_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run_logs: Mapped[list["RunLog"]] = relationship("RunLog", back_populates="user")


class RunLog(Base):
    __tablename__ = "run_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger: Mapped[str | None] = mapped_column(String, nullable=True)
    sites_attempted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sites_succeeded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_masked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sheet_url: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped[User | None] = relationship("User", back_populates="run_logs")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
