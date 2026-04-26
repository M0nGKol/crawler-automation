from __future__ import annotations

from auth import get_google_sheets_client
from database import User
from mvp import Job


async def setup_new_user_workspace(
    user: User,
    encrypted_token: str,
    company: str,
    db,
) -> dict:
    gc = get_google_sheets_client(encrypted_token)
    ss = gc.create(f"Healthcare Jobs — {company}")

    ws_masked = ss.sheet1
    ws_masked.update_title("Jobs Masked")
    ws_masked.append_row(Job.HEADERS)

    ws_raw = ss.add_worksheet("Jobs Raw", rows=1000, cols=len(Job.HEADERS))
    ws_raw.append_row(Job.HEADERS)

    ws_log = ss.add_worksheet("Run Log", rows=1000, cols=7)
    ws_log.append_row(
        [
            "run_id",
            "started_at",
            "finished_at",
            "trigger",
            "sites_scraped",
            "listings_found",
            "errors",
        ]
    )

    ws_dashboard = ss.add_worksheet("Dashboard", rows=100, cols=4)
    ws_dashboard.update("A1:B4", [["Metric", "Value"], ["Last run", "Never"], ["Total listings", 0], ["Sites active", 11]])

    try:
        default_tab = ss.worksheet("Sheet1")
        ss.del_worksheet(default_tab)
    except Exception:
        pass

    user.sheet_id = ss.id
    user.sites_config = None
    user.google_token = encrypted_token
    db.commit()

    return {
        "sheet_id": ss.id,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{ss.id}",
        "sheet_title": f"Healthcare Jobs — {company}",
    }
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from database import User

SITES_TEMPLATE_PATH = Path("config/sites.yaml")


def load_default_sites() -> list[dict[str, Any]]:
  if not SITES_TEMPLATE_PATH.exists():
    return []
  with SITES_TEMPLATE_PATH.open("r", encoding="utf-8") as file:
    data = yaml.safe_load(file) or {}
  return data.get("sites", [])


def setup_user_sheet(db: Session, user_email: str, sheet_id: str) -> User:
  user = db.query(User).filter(User.email == user_email).first()
  if not user:
    user = User(email=user_email, sheet_id=sheet_id)
    db.add(user)
  else:
    user.sheet_id = sheet_id

  db.commit()
  db.refresh(user)
  return user
