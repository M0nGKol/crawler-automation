"""
Google Sheets output sink.

Writes raw job data to the 'raw_data' tab and masked data to the
'masked_data' tab. Both tabs share the same 13-column schema so
rows can be cross-referenced by the shared job id.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from auth import get_google_sheets_client
from database import SessionLocal, User
from models import JOB_HEADERS, JobMasked, JobRaw

if TYPE_CHECKING:
    import gspread

log = logging.getLogger(__name__)


def _get_or_create_tab(
    ss: "gspread.Spreadsheet",
    tab_name: str,
    headers: list[str],
) -> "gspread.Worksheet":
    """Return existing worksheet or create it and write the header row."""
    try:
        import gspread as _gspread  # noqa: F401

        ws = ss.worksheet(tab_name)
        # Ensure headers exist on row 1
        existing = ws.row_values(1)
        if not existing:
            ws.append_row(headers, value_input_option="USER_ENTERED")
        return ws
    except Exception as not_found:
        # gspread raises WorksheetNotFound — create a fresh tab
        # Note: The exception string might just be the tab name (e.g., "raw_data"),
        # so we also check the class name.
        err_str = str(not_found).lower()
        class_name = not_found.__class__.__name__.lower()
        
        if "not found" in err_str or "worksheet" in err_str or "notfound" in class_name:
            ws = ss.add_worksheet(tab_name, rows=5000, cols=len(headers))
            ws.append_row(headers, value_input_option="USER_ENTERED")
            return ws
        raise


def _get_existing_ids(ws: "gspread.Worksheet") -> set[str]:
    """Fetch all IDs from column 1 to skip duplicates before appending."""
    try:
        values = ws.col_values(1)
        # Skip header row
        return set(values[1:]) if len(values) > 1 else set()
    except Exception:
        return set()


def write_to_sheets(
    jobs_raw: list[JobRaw],
    jobs_masked: list[JobMasked],
    sheet_id: str = "",
    creds_path: str = "",
    user_id: str | None = None,
) -> str | None:
    """
    Write jobs_raw → 'raw_data' tab and jobs_masked → 'masked_data' tab.

    Returns the spreadsheet URL or None on failure.
    """
    log.info(f"[SHEETS] Starting write - requested sheet_id: {sheet_id}, user_id: {user_id}")
    log.info(f"[SHEETS] Jobs to write - raw: {len(jobs_raw)}, masked: {len(jobs_masked)}")
    
    effective_sheet_id = sheet_id
    gc = None

    if user_id:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.google_token and user.sheet_id:
                gc = get_google_sheets_client(user.google_token)
                effective_sheet_id = user.sheet_id
                log.info(f"[SHEETS] Loaded credentials for user {user_id}. Using sheet {effective_sheet_id}")
            else:
                log.warning(f"[SHEETS] User {user_id} found but missing token or sheet_id")
        except Exception as e:
            log.error(f"[SHEETS] Error loading user credentials: {e}")
        finally:
            db.close()

    if not effective_sheet_id:
        effective_sheet_id = os.getenv("SHEET_DEFAULT", "")

    if not effective_sheet_id:
        log.error("[SHEETS] No spreadsheet_id provided - skipping")
        return None

    if not gc and not creds_path:
        log.error("[SHEETS] No credentials provided - skipping")
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

        # ── raw_data tab ──────────────────────────────────────────────────
        ws_raw = _get_or_create_tab(ss, "raw_data", JOB_HEADERS)
        existing_raw_ids = _get_existing_ids(ws_raw)
        new_raw_rows = [
            j.to_row() for j in jobs_raw if j.id not in existing_raw_ids
        ]
        if new_raw_rows:
            ws_raw.append_rows(new_raw_rows, value_input_option="USER_ENTERED")
            log.info("━━ raw_data tab: appended %d new rows", len(new_raw_rows))
        else:
            log.info("━━ raw_data tab: no new rows to append (all duplicates)")

        # ── masked_data tab ───────────────────────────────────────────────
        ws_masked = _get_or_create_tab(ss, "masked_data", JOB_HEADERS)
        existing_masked_ids = _get_existing_ids(ws_masked)
        new_masked_rows = [
            j.to_row() for j in jobs_masked if j.id not in existing_masked_ids
        ]
        if new_masked_rows:
            ws_masked.append_rows(new_masked_rows, value_input_option="USER_ENTERED")
            log.info("━━ masked_data tab: appended %d new rows", len(new_masked_rows))
        else:
            log.info("━━ masked_data tab: no new rows to append (all duplicates)")

        sheet_url = f"https://docs.google.com/spreadsheets/d/{effective_sheet_id}"
        log.info(f"[SHEETS] Successfully wrote {len(new_raw_rows)} raw rows and {len(new_masked_rows)} masked rows")
        log.info(f"[SHEETS] URL: {sheet_url}")
        return sheet_url

    except ImportError:
        log.warning("[SHEETS] gspread not installed — run: pip install gspread google-auth")
    except Exception as exc:
        log.error(f"[SHEETS] Failed to write: {exc}", exc_info=True)
        raise
    return None


# ── Backward-compat shim so old callers still work ────────────────────────
def save_sheets(
    jobs: list,  # legacy list[Job]
    sheet_id: str = "",
    creds_path: str = "",
    user_id: str | None = None,
) -> str | None:
    """
    Legacy shim: converts old-style Job objects to JobRaw/JobMasked and
    writes them to Sheets. Kept for backward compatibility.
    """
    from models import JobRaw, JobMasked  # local import avoids circular

    raw: list[JobRaw] = []
    masked: list[JobMasked] = []
    for j in jobs:
        raw.append(
            JobRaw(
                id=getattr(j, "id", ""),
                source=getattr(j, "source", ""),
                facility=getattr(j, "raw_facility", ""),
                job_title=getattr(j, "job_title", ""),
                location=getattr(j, "location", ""),
                job_description=getattr(j, "job_description", ""),
                requirements=getattr(j, "requirements", ""),
                salary=getattr(j, "salary_raw", ""),
                employment_type=getattr(j, "employment_type", ""),
                application_deadline=getattr(j, "application_deadline", ""),
                contact_information=getattr(j, "contact_information", ""),
                url=getattr(j, "url", ""),
                scraped_at=getattr(j, "scraped_at", ""),
            )
        )
        masked.append(
            JobMasked(
                id=getattr(j, "id", ""),
                source=getattr(j, "source", ""),
                facility=getattr(j, "masked_facility", "●●●") or "●●●",
                job_title=getattr(j, "job_title", ""),
                location=getattr(j, "location", ""),
                job_description=getattr(j, "job_description", ""),
                requirements=getattr(j, "requirements", ""),
                salary=getattr(j, "salary_masked", "●●●") or "●●●",
                employment_type=getattr(j, "employment_type", ""),
                application_deadline=getattr(j, "application_deadline", ""),
                contact_information=getattr(j, "contact_information", ""),
                url=getattr(j, "url", ""),
                scraped_at=getattr(j, "scraped_at", ""),
            )
        )
    return write_to_sheets(raw, masked, sheet_id=sheet_id, creds_path=creds_path, user_id=user_id)
