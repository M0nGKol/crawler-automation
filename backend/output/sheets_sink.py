from __future__ import annotations

import logging
import os

from auth import get_google_sheets_client
from database import SessionLocal, User
from domain.job import Job

log = logging.getLogger(__name__)


def save_sheets(jobs: list[Job], sheet_id: str, creds_path: str, user_id: str | None = None) -> str | None:
    effective_sheet_id = sheet_id
    gc = None

    if user_id:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.google_token and user.sheet_id:
                gc = get_google_sheets_client(user.google_token)
                effective_sheet_id = user.sheet_id
        finally:
            db.close()

    if not effective_sheet_id:
        effective_sheet_id = os.getenv("SHEET_DEFAULT", "")

    if not effective_sheet_id:
        log.info("━━ GOOGLE_SHEET_ID not set — skipping Sheets upload")
        return None

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        if not gc:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.file",
            ]
            creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
            gc = gspread.authorize(creds)
        ss = gc.open_by_key(effective_sheet_id)

        try:
            ws_masked = ss.worksheet("Jobs Masked")
        except gspread.WorksheetNotFound:
            ws_masked = ss.add_worksheet("Jobs Masked", rows=1000, cols=len(Job.HEADERS))
            ws_masked.append_row(Job.HEADERS)

        try:
            ws_raw = ss.worksheet("Jobs Raw")
        except gspread.WorksheetNotFound:
            ws_raw = ss.add_worksheet("Jobs Raw", rows=1000, cols=len(Job.HEADERS))
            ws_raw.append_row(Job.HEADERS)

        rows = [j.to_row() for j in jobs]
        ws_masked.append_rows(rows, value_input_option="USER_ENTERED")
        ws_raw.append_rows(rows, value_input_option="USER_ENTERED")

        log.info("━━ Google Sheets updated → %d rows written", len(rows))
        log.info("   https://docs.google.com/spreadsheets/d/%s", effective_sheet_id)
        return f"https://docs.google.com/spreadsheets/d/{effective_sheet_id}"
    except ImportError:
        log.warning("gspread not installed — run: pip install gspread google-auth")
    except Exception as exc:
        log.error("Sheets upload failed: %s", exc)
    return None
