from __future__ import annotations

import logging
import os
import uuid

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, func, text
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship, sessionmaker

log = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./crawler.db")

_engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)
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
    sheets: Mapped[list["UserSheet"]] = relationship("UserSheet", back_populates="user", order_by="UserSheet.created_at")


class RunLog(Base):
    __tablename__ = "run_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    sites_attempted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sites_succeeded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sites_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_masked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sheet_url: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped[User | None] = relationship("User", back_populates="run_logs")


class JobHash(Base):
    """Stores MD5 hashes of scraped jobs to enable cross-run deduplication."""

    __tablename__ = "job_hashes"

    hash: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScraperSite(Base):
    """Tracks all scraper sites (default + custom) with per-user overrides."""

    __tablename__ = "scraper_sites"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    site_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String, default="", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_status: Mapped[str] = mapped_column(String, default="unknown", nullable=False)
    last_job_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)

    user: Mapped[User | None] = relationship("User")


class UserSheet(Base):
    """
    One row per Google Sheet owned by a user.
    Replaces the single user.sheet_id column — a user can now have many sheets.
    The active sheet (used by the pipeline by default) is flagged with is_default=True.
    Only one row per user should have is_default=True at a time.
    """

    __tablename__ = "user_sheets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    sheet_id: Mapped[str] = mapped_column(String, nullable=False)          # Google Sheets file ID
    sheet_title: Mapped[str] = mapped_column(String, default="", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="sheets")


class OAuthState(Base):
    """Persistent OAuth state tokens — replaces in-memory dict so multi-instance deploys work."""

    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String, primary_key=True)
    return_to: Mapped[str] = mapped_column(String, default="/dashboard", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── SQLite migration helpers ──────────────────────────────────────────────
_RUN_LOG_MIGRATIONS = [
    "ALTER TABLE run_logs ADD COLUMN status TEXT DEFAULT 'pending'",
    "ALTER TABLE run_logs ADD COLUMN sites_failed INTEGER DEFAULT 0",
    "ALTER TABLE run_logs ADD COLUMN jobs_found INTEGER DEFAULT 0",
]

_SCRAPER_SITE_MIGRATIONS = [
    "ALTER TABLE scraper_sites ADD COLUMN last_job_count INTEGER DEFAULT 0",
    "ALTER TABLE scraper_sites ADD COLUMN consecutive_failures INTEGER DEFAULT 0",
]

_POSTGRES_SCRAPER_SITE_MIGRATIONS = [
    "ALTER TABLE scraper_sites ADD COLUMN IF NOT EXISTS last_job_count INTEGER DEFAULT 0",
    "ALTER TABLE scraper_sites ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER DEFAULT 0",
]


def _run_migrations(conn) -> None:  # type: ignore[no-untyped-def]
    """Apply ALTER TABLE migrations that SQLite's create_all won't handle."""
    for stmt in [*_RUN_LOG_MIGRATIONS, *_SCRAPER_SITE_MIGRATIONS]:
        try:
            conn.execute(text(stmt))
            conn.commit()
        except Exception:
            # Column already exists — safe to ignore
            pass


def _run_postgres_compat_migrations(conn) -> None:  # type: ignore[no-untyped-def]
    """Apply idempotent Postgres migrations for columns expected by ORM models."""
    for stmt in _POSTGRES_SCRAPER_SITE_MIGRATIONS:
        try:
            conn.execute(text(stmt))
            conn.commit()
        except Exception as exc:
            log.warning("Postgres compat migration failed (%s): %s", stmt, exc)
            conn.rollback()


def _backfill_user_sheets(conn) -> None:
    """
    One-time migration: copy every user's existing sheet_id into the new
    user_sheets table as their default sheet, skipping users who already
    have a row there (idempotent — safe to run on every startup).
    """
    try:
        rows = conn.execute(
            text("SELECT id, sheet_id, company FROM users WHERE sheet_id IS NOT NULL AND sheet_id != ''")
        ).fetchall()
        for row in rows:
            user_id, sheet_id, company = row[0], row[1], row[2] or "My Sheet"
            existing = conn.execute(
                text("SELECT id FROM user_sheets WHERE user_id = :uid AND sheet_id = :sid"),
                {"uid": user_id, "sid": sheet_id},
            ).fetchone()
            if not existing:
                conn.execute(
                    text(
                        "INSERT INTO user_sheets (id, user_id, sheet_id, sheet_title, is_default, created_at) "
                        "VALUES (:id, :user_id, :sheet_id, :title, 1, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "id": uuid.uuid4().hex,
                        "user_id": user_id,
                        "sheet_id": sheet_id,
                        "title": f"Healthcare Jobs — {company}",
                    },
                )
        conn.commit()
        log.info("[DB] user_sheets backfill complete (%d users processed)", len(rows))
    except Exception as exc:
        log.warning("[DB] user_sheets backfill failed (non-fatal): %s", exc)
        try:
            conn.rollback()
        except Exception:
            pass


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            _run_migrations(conn)
            _backfill_user_sheets(conn)
    elif engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            _run_postgres_compat_migrations(conn)
            _backfill_user_sheets(conn)
