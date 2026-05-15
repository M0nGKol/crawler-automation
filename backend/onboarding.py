from __future__ import annotations

import uuid

from auth import get_google_sheets_client
from database import User, UserSheet
from models import MASKED_JOB_HEADERS, RAW_JOB_HEADERS


def _build_sheet_structure(ss, sheet_title: str) -> None:
    """Set up the standard tabs (Jobs Masked, Jobs Raw, Run Log, Dashboard) on a sheet."""
    ws_masked = ss.sheet1
    ws_masked.update_title("Jobs Masked")
    ws_masked.append_row(MASKED_JOB_HEADERS)

    ws_raw = ss.add_worksheet("Jobs Raw", rows=1000, cols=len(RAW_JOB_HEADERS))
    ws_raw.append_row(RAW_JOB_HEADERS)

    ws_log = ss.add_worksheet("Run Log", rows=1000, cols=7)
    ws_log.append_row(["run_id", "started_at", "finished_at", "trigger", "sites_scraped", "listings_found", "errors"])

    ws_dashboard = ss.add_worksheet("Dashboard", rows=100, cols=4)
    ws_dashboard.update(
        "A1:B4",
        [["Metric", "Value"], ["Last run", "Never"], ["Total listings", 0], ["Sites active", 11]],
    )

    try:
        ss.del_worksheet(ss.worksheet("Sheet1"))
    except Exception:
        pass


async def setup_new_user_workspace(
    user: User,
    encrypted_token: str,
    company: str,
    db,
) -> dict:
    """
    Called during onboarding. Creates the user's first Google Sheet,
    saves it as their default sheet in UserSheet, and keeps user.sheet_id
    updated for backward compatibility.
    """
    gc = get_google_sheets_client(encrypted_token)
    sheet_title = f"Healthcare Jobs — {company}"
    ss = gc.create(sheet_title)

    _build_sheet_structure(ss, sheet_title)

    # Persist to User (backward compat) + UserSheet table
    user.sheet_id = ss.id
    user.sites_config = None
    user.google_token = encrypted_token

    # Mark all existing sheets for this user as non-default before adding the new one
    for existing in db.query(UserSheet).filter(UserSheet.user_id == user.id).all():
        existing.is_default = False

    user_sheet = UserSheet(
        id=uuid.uuid4().hex,
        user_id=user.id,
        sheet_id=ss.id,
        sheet_title=sheet_title,
        is_default=True,
    )
    db.add(user_sheet)
    db.commit()

    return {
        "sheet_id": ss.id,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{ss.id}",
        "sheet_title": sheet_title,
    }


async def create_additional_sheet(
    user: User,
    sheet_title: str,
    db,
) -> dict:
    """
    Create a new Google Sheet for an existing user without changing their default.
    Called from POST /sheets/create.
    """
    gc = get_google_sheets_client(user.google_token)
    ss = gc.create(sheet_title)

    _build_sheet_structure(ss, sheet_title)

    user_sheet = UserSheet(
        id=uuid.uuid4().hex,
        user_id=user.id,
        sheet_id=ss.id,
        sheet_title=sheet_title,
        is_default=False,
    )
    db.add(user_sheet)
    db.commit()
    db.refresh(user_sheet)

    return {
        "id": user_sheet.id,
        "sheet_id": ss.id,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{ss.id}",
        "sheet_title": sheet_title,
        "is_default": False,
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
