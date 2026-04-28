from __future__ import annotations

import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import Base, JobHash, RunLog, ScraperSite, User

SQLITE_URL = "sqlite:///./backend/crawler.db"
TABLES = [User, RunLog, JobHash, ScraperSite]


def _to_dict(model_obj, columns: list[str]) -> dict[str, object]:
    return {column: getattr(model_obj, column) for column in columns}


def _count_rows(db: Session, model) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def main() -> None:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is empty. Set Neon/Postgres URL in backend/.env before running.")
    if database_url.startswith("sqlite"):
        raise RuntimeError("DATABASE_URL points to SQLite. Set it to a Postgres/Neon URL first.")

    source_engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
    target_engine = create_engine(database_url)

    SourceSession = sessionmaker(bind=source_engine, autocommit=False, autoflush=False)
    TargetSession = sessionmaker(bind=target_engine, autocommit=False, autoflush=False)

    Base.metadata.create_all(bind=target_engine)

    with SourceSession() as source_db, TargetSession() as target_db:
        for model in TABLES:
            columns = [column.name for column in model.__table__.columns]
            source_rows = source_db.execute(select(model)).scalars().all()
            for row in source_rows:
                target_db.merge(model(**_to_dict(row, columns)))
            target_db.commit()

            source_count = _count_rows(source_db, model)
            target_count = _count_rows(target_db, model)
            print(f"{model.__tablename__}: source={source_count} target={target_count}")

    print("SQLite to Neon migration complete.")


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    main()
