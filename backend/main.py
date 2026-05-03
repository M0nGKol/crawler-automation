from __future__ import annotations

import json
import logging
import os
import re
import secrets
import urllib.parse
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

# Load .env BEFORE any module that reads os.getenv at import time (e.g. auth.py)
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, HttpUrl
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import (
    create_jwt,
    encrypt_token,
    exchange_code_for_token,
    get_google_auth_url,
    GOOGLE_OAUTH_REDIRECT_URI,
    GOOGLE_SCOPES,
    get_google_sheets_client,
    get_user_info,
    hash_password,
    verify_jwt,
    verify_password,
)
from database import OAuthState, RunLog, ScraperSite, SessionLocal, User, get_db, init_db
from app.config import load_sites_config, merge_sites, parse_sites_yaml
from mvp import run_scraper
from onboarding import setup_new_user_workspace
from pipeline import run_pipeline

FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
INTERNAL_ADMIN_KEY = os.getenv("INTERNAL_ADMIN_KEY", "")
log = logging.getLogger(__name__)


def _require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    """Guard for legacy email/password endpoints — only accessible with a server-side key."""
    if not INTERNAL_ADMIN_KEY or x_internal_key != INTERNAL_ADMIN_KEY:
        raise HTTPException(status_code=404, detail="Not found")


def _normalize_return_to(return_to: str | None) -> str:
    if not return_to:
        return "/dashboard"
    if not return_to.startswith("/") or return_to.startswith("//"):
        return "/dashboard"
    return return_to


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # Seed default scraper sites on startup
    try:
        from app.config import load_sites_config
        from pathlib import Path
        default_sites = load_sites_config(Path("config/sites.yaml"))
        from pipeline import _seed_scraper_sites
        _seed_scraper_sites(default_sites)
    except Exception as _seed_err:
        import logging
        logging.getLogger(__name__).warning("Site seeding failed: %s", _seed_err)
    yield


app = FastAPI(title="Health Care Crawler API", lifespan=lifespan)

# ── CORS ────────────────────────────────────────────────────────────────
_allowed_origins = [o for o in [
    FRONTEND_URL,                                           # e.g. https://crawler-automation.vercel.app
    os.getenv("NEXTAUTH_URL", ""),                         # mirror of FRONTEND_URL used by NextAuth
    "https://crawler-automation.vercel.app",               # explicit production fallback
    "https://crawler-automation-1.onrender.com",           # Render backend (for same-origin browser calls)
    "http://localhost:3000",                               # local dev only
] if o]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    # Explicitly include PUT/OPTIONS for site toggle preflight + request.
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    company: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SyncRequest(BaseModel):
    email: EmailStr
    name: str | None = None


class RunRequest(BaseModel):
    user_id: str | None = None


class SitesPayload(BaseModel):
    sites: dict[str, Any]


class AddSiteRequest(BaseModel):
    url: HttpUrl
    type: str = "job_board"
    mode: str = "claude_fallback"
    site_id: str | None = None


class NewSiteRequest(BaseModel):
    """Request body for POST /sites/add (DB-backed sites API)."""
    url: str
    site_name: str


class SiteToggleRequest(BaseModel):
    is_active: bool


def _slugify_site_name(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return slug or f"site_{secrets.token_hex(4)}"


def _default_site_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.replace("www.", "")
    path = parsed.path.strip("/").replace("/", "_")
    return _slugify_site_name(f"{host}_{path}" if path else host)


def _load_default_sites() -> dict[str, Any]:
    backend_dir = Path(__file__).resolve().parent
    candidate_paths = [
        backend_dir / "sites.yml",
        backend_dir / "config" / "sites.yml",
        backend_dir / "config" / "sites.yaml",
    ]
    yaml_path = next((path for path in candidate_paths if path.exists()), None)
    if not yaml_path:
        return {}

    with open(yaml_path, "r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}
    return loaded.get("sites", {})


def load_sites_from_yaml() -> list[dict[str, Any]]:
    """Load default sites from YAML for /sites/list response."""
    backend_dir = Path(__file__).resolve().parent
    candidate_paths = [
        backend_dir / "sites.yml",
        backend_dir / "config" / "sites.yml",
        backend_dir / "config" / "sites.yaml",
    ]
    yaml_path = next((path for path in candidate_paths if path.exists()), None)
    if not yaml_path:
        return []

    with open(yaml_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    sites = []
    for site_name, config in (data.get("sites") or {}).items():
        sites.append(
            {
                "id": site_name,
                "site_name": site_name,
                "url": config.get("url", ""),
                "type": config.get("type", ""),
                "is_default": True,
                "is_active": bool(config.get("active", False)),
            }
        )
    return sites


def _require_user_from_jwt(authorization: str | None, db: Session) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.replace("Bearer ", "", 1).strip()
    user_id = verify_jwt(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── Sync endpoint (called by NextAuth on sign-in) ──────────────────────
@app.post("/auth/sync")
def auth_sync(payload: SyncRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Find-or-create a user by email.  Returns the fields NextAuth stores in its JWT."""
    user = db.query(User).filter(User.email == str(payload.email)).first()
    if not user:
        user = User(
            email=str(payload.email),
            name=payload.name,
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if payload.name and not user.name:
            user.name = payload.name
            db.commit()
    return {
        "user_id": user.id,
        "sheet_id": user.sheet_id,
        "role": user.role,
    }


@app.post("/auth/register")
def auth_register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal_key),
) -> dict[str, str]:
    exists = db.query(User).filter(User.email == payload.email).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=str(payload.email),
        name=payload.name,
        company=payload.company,
        role="admin",
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user_id": user.id, "message": "Account created"}


@app.get("/auth/google")
def auth_google(
    return_to: str = Query(default="/dashboard"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.query(OAuthState).filter(OAuthState.created_at < cutoff).delete()
    db.commit()

    state = secrets.token_urlsafe(32)
    db.add(OAuthState(state=state, return_to=_normalize_return_to(return_to)))
    db.commit()

    return RedirectResponse(url=get_google_auth_url(state))


@app.get("/auth/google/config")
def auth_google_config() -> dict[str, Any]:
    return {
        "backend_redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
        "required_scopes": GOOGLE_SCOPES,
        "frontend_nextauth_callback": f"{FRONTEND_URL}/api/auth/callback/google",
    }


@app.get("/auth/google/callback")
async def auth_google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

        state_record = db.query(OAuthState).filter(OAuthState.state == state).first()
        if not state_record:
            raise ValueError("Invalid or expired OAuth state")
        created_at = state_record.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at < cutoff:
            db.delete(state_record)
            db.commit()
            raise ValueError("OAuth state expired — please try signing in again")

        return_to = _normalize_return_to(state_record.return_to)
        db.delete(state_record)
        db.query(OAuthState).filter(OAuthState.created_at < cutoff).delete()
        db.commit()

        token = exchange_code_for_token(code)
        user_info = get_user_info(token)
        encrypted_token = encrypt_token(token)

        email = user_info.get("email")
        name = user_info.get("name")
        if not email:
            raise ValueError("Google did not return an email address")

        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, name=name, role="admin")
            db.add(user)
            db.commit()
            db.refresh(user)

        if not user.sheet_id:
            await setup_new_user_workspace(
                user=user,
                encrypted_token=encrypted_token,
                company=name or email,
                db=db,
            )
        else:
            user.google_token = encrypted_token
            user.last_login = datetime.now(timezone.utc)
            db.commit()

        jwt_token = create_jwt(user.id)
        url = (
            f"{FRONTEND_URL}/auth/callback"
            f"?token={urllib.parse.quote(jwt_token, safe='')}"
            f"&return_to={urllib.parse.quote(return_to, safe='')}"
            f"&user_id={urllib.parse.quote(user.id, safe='')}"
        )
        return RedirectResponse(url=url)
    except Exception as exc:
        error = urllib.parse.quote(str(exc), safe="")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error={error}")


@app.post("/auth/login")
def auth_login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal_key),
) -> dict[str, str]:
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    return {
        "token": create_jwt(user.id),
        "user_id": user.id,
        "email": user.email,
        "company": user.company or "",
        "role": user.role,
    }


@app.get("/auth/me")
def auth_me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _require_user_from_jwt(authorization, db)
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "company": user.company,
        "role": user.role,
        "sheet_id": user.sheet_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


@app.get("/auth/sheets/status")
def auth_sheets_status(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user = _require_user_from_jwt(authorization, db)
    if not user.google_token or not user.sheet_id:
        return {"connected": False}
    try:
        gc = get_google_sheets_client(user.google_token)
        ss = gc.open_by_key(user.sheet_id)
        return {
            "connected": True,
            "sheet_title": ss.title,
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{user.sheet_id}",
            "tab_count": len(ss.worksheets()),
        }
    except Exception:
        return {"connected": False}


@app.post("/run")
async def run_pipeline_endpoint(
    payload: RunRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Start pipeline in background. Returns run_id immediately for polling."""
    user: User | None = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
        user_id = verify_jwt(token)
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
    if not user and payload.user_id:
        user = db.query(User).filter(User.id == payload.user_id).first()

    run_log = RunLog(
        id=uuid.uuid4().hex,
        user_id=user.id if user else None,
        started_at=datetime.now(timezone.utc),
        trigger="api",
        status="running",
    )
    db.add(run_log)
    db.commit()
    db.refresh(run_log)
    run_id = run_log.id

    async def _run_in_background() -> None:
        """Execute the pipeline and update the run_log when done."""
        _db = SessionLocal()
        try:
            result = await run_pipeline(user_id=user.id if user else None, run_id=run_id)
            _log = _db.query(RunLog).filter(RunLog.id == run_id).first()
            if _log:
                _log.finished_at = datetime.now(timezone.utc)
                _log.status = "completed"
                _log.sites_attempted = result.get("sites_attempted", 0)
                _log.sites_succeeded = result.get("sites_succeeded", 0)
                _log.sites_failed = result.get("sites_failed", 0)
                _log.listings_scraped = result.get("count", 0)
                _log.listings_masked = result.get("count", 0)
                _log.jobs_found = result.get("count", 0)
                _log.sheet_url = result.get("sheet_url")
                _db.commit()
        except Exception as exc:
            _log = _db.query(RunLog).filter(RunLog.id == run_id).first()
            if _log:
                _log.finished_at = datetime.now(timezone.utc)
                _log.status = "failed"
                _log.errors = str(exc)
                _db.commit()
        finally:
            _db.close()

    background_tasks.add_task(_run_in_background)
    return {"run_id": run_id, "status": "started"}


@app.get("/run/{run_id}")
def get_run_status(
    run_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Poll the status of a pipeline run."""
    row = db.query(RunLog).filter(RunLog.id == run_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": row.id,
        "status": getattr(row, "status", "unknown"),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.finished_at.isoformat() if row.finished_at else None,
        "jobs_found": getattr(row, "jobs_found", 0),
        "sites_succeeded": row.sites_succeeded,
        "sites_failed": getattr(row, "sites_failed", 0),
        "sheet_url": row.sheet_url,
        "errors": row.errors,
    }



@app.get("/status")
def status(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _require_user_from_jwt(authorization, db)
    runs = (
        db.query(RunLog)
        .filter(RunLog.user_id == user.id)
        .order_by(RunLog.started_at.desc())
        .limit(1)
        .all()
    )
    last = runs[0] if runs else None
    return {
        "status": "ok",
        "user_id": user.id,
        "last_run": last.started_at.isoformat() if last and last.started_at else None,
    }


@app.get("/logs")
def logs(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _require_user_from_jwt(authorization, db)
    rows = (
        db.query(RunLog)
        .filter(RunLog.user_id == user.id)
        .order_by(RunLog.started_at.desc())
        .limit(50)
        .all()
    )
    return {
        "logs": [
            {
                "id": row.id,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "trigger": row.trigger,
                "sites_attempted": row.sites_attempted,
                "sites_succeeded": row.sites_succeeded,
                "listings_scraped": row.listings_scraped,
                "errors": row.errors,
                "sheet_url": row.sheet_url,
            }
            for row in rows
        ]
    }


@app.get("/sites")
def get_sites(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _require_user_from_jwt(authorization, db)
    default_sites = _load_default_sites()
    user_sites = parse_sites_yaml(user.sites_config)
    merged = merge_sites(default_sites, user_sites)
    return {
        "sites": merged,
        "default_sites": default_sites,
        "custom_sites": user_sites,
    }


@app.post("/sites")
def create_sites(
    payload: SitesPayload,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = _require_user_from_jwt(authorization, db)
    user.sites_config = yaml.safe_dump({"sites": payload.sites}, allow_unicode=True)
    db.commit()
    return {"message": "Sites config updated"}


@app.put("/sites/{site_id}")
def toggle_site(
    site_id: str,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    current_user = _require_user_from_jwt(authorization, db)
    is_active = bool(payload.get("is_active", True))
    log.info("[TOGGLE] site_id=%s is_active=%s user=%s", site_id, is_active, current_user.id)

    # Default sites use YAML keys as `id` (not the DB row id), so detect defaults
    # by checking the YAML site map.
    default_site_names = set(_load_default_sites().keys())
    if site_id in default_site_names:
        # Persist user preference for default sites.
        try:
            db.execute(
                text(
                    """
                    INSERT INTO user_site_prefs (user_id, site_id, is_active)
                    VALUES (:user_id, :site_id, :is_active)
                    ON CONFLICT (user_id, site_id) DO UPDATE SET
                        is_active = EXCLUDED.is_active
                    """
                ),
                {"user_id": current_user.id, "site_id": site_id, "is_active": is_active},
            )
            db.commit()
        except Exception:
            # Table might not exist yet.
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS user_site_prefs (
                        user_id TEXT NOT NULL,
                        site_id TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, site_id)
                    )
                    """
                )
            )
            db.commit()
            db.execute(
                text(
                    """
                    INSERT INTO user_site_prefs (user_id, site_id, is_active)
                    VALUES (:user_id, :site_id, :is_active)
                    ON CONFLICT (user_id, site_id) DO UPDATE SET
                        is_active = EXCLUDED.is_active
                    """
                ),
                {"user_id": current_user.id, "site_id": site_id, "is_active": is_active},
            )
            db.commit()

        return {"success": True, "site_id": site_id, "is_active": is_active}

    # Custom site: update the scraper_sites row by DB id.
    site = db.query(ScraperSite).filter(ScraperSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorised")

    site.is_active = is_active
    db.commit()
    return {"success": True, "site_id": site_id, "is_active": is_active}


@app.post("/sites/add-url")
def add_site_url(
    payload: AddSiteRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user = _require_user_from_jwt(authorization, db)
    sites = parse_sites_yaml(user.sites_config)

    proposed_id = payload.site_id or _default_site_name_from_url(str(payload.url))
    site_id = _slugify_site_name(proposed_id)
    if not site_id:
        raise HTTPException(status_code=400, detail="Invalid site_id")

    sites[site_id] = {
        "url": str(payload.url),
        "type": payload.type,
        "mode": payload.mode,
    }
    user.sites_config = yaml.safe_dump({"sites": sites}, allow_unicode=True)
    db.commit()

    return {
        "message": "Custom site added",
        "site_id": site_id,
        "site": sites[site_id],
    }


@app.get("/export")
def export_data(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _require_user_from_jwt(authorization, db)
    return {
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{user.sheet_id}" if user.sheet_id else None,
        "sheet_id": user.sheet_id,
    }


# ── New DB-backed sites API (Task 8) ─────────────────────────────────────────

@app.post("/sites/add")
def add_custom_site(
    payload: NewSiteRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Add a user-defined custom site to the DB."""
    user = _require_user_from_jwt(authorization, db)
    # Check for duplicate site_name
    existing = db.query(ScraperSite).filter(ScraperSite.site_name == payload.site_name).first()
    if existing:
        raise HTTPException(status_code=409, detail="site_name already exists")
    site = ScraperSite(
        id=uuid.uuid4().hex,
        site_name=payload.site_name,
        url=str(payload.url),
        is_default=False,
        is_active=True,
        last_status="unknown",
        user_id=user.id,
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    return _format_site(site)


@app.get("/sites/list")
def list_sites(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return YAML default sites + active custom sites for current user."""
    user = _require_user_from_jwt(authorization, db)
    default_sites = load_sites_from_yaml()

    # Apply per-user activation preferences for default sites.
    pref_map: dict[str, bool] = {}
    try:
        prefs = db.execute(
            text(
                """
                SELECT site_id, is_active
                FROM user_site_prefs
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user.id},
        ).mappings().all()
        pref_map = {str(r["site_id"]): bool(r["is_active"]) for r in prefs}
    except Exception:
        pref_map = {}

    custom_sites: list[dict[str, Any]] = []
    try:
        # Return all custom sites (active + inactive) so the UI can toggle them.
        rows = db.execute(
            text(
                """
                SELECT id, site_name, url, is_default, is_active
                FROM scraper_sites
                WHERE user_id = :user_id AND is_default = FALSE
                ORDER BY site_name
                """
            ),
            {"user_id": user.id},
        ).mappings().all()
        custom_sites = [
            {
                "id": row.get("id"),
                "site_name": row.get("site_name", ""),
                "url": row.get("url", ""),
                "type": "custom",
                "is_default": bool(row.get("is_default", False)),
                "is_active": bool(row.get("is_active", True)),
            }
            for row in rows
        ]
    except Exception:
        custom_sites = []

    for site in default_sites:
        if str(site["id"]) in pref_map:
            site["is_active"] = bool(pref_map[str(site["id"])])

    return {"sites": default_sites + custom_sites}


@app.put("/sites/{site_id}/toggle")
def toggle_site(
    site_id: str,
    payload: SiteToggleRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Toggle is_active for any site the user can see."""
    user = _require_user_from_jwt(authorization, db)
    site = db.query(ScraperSite).filter(ScraperSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    # Allow toggling default sites and user's own custom sites
    if not site.is_default and site.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorised")
    site.is_active = payload.is_active
    db.commit()
    db.refresh(site)
    return _format_site(site)


@app.delete("/sites/{site_id}")
def delete_custom_site(
    site_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Delete a custom (non-default) site. Default sites cannot be deleted."""
    user = _require_user_from_jwt(authorization, db)
    site = db.query(ScraperSite).filter(ScraperSite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if site.is_default:
        raise HTTPException(status_code=403, detail="Cannot delete default sites")
    if site.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorised")
    db.delete(site)
    db.commit()
    return {"message": "Site deleted"}


def _format_site(site: ScraperSite) -> dict[str, Any]:
    return {
        "id": site.id,
        "site_name": site.site_name,
        "url": site.url,
        "type": "custom" if not site.is_default else "default",
        "mode": "db",
        "is_default": site.is_default,
        "is_active": site.is_active,
        "last_status": site.last_status,
        "status_note": "",
        "last_job_count": getattr(site, "last_job_count", 0),
        "consecutive_failures": getattr(site, "consecutive_failures", 0),
        "last_run_at": site.last_run_at.isoformat() if site.last_run_at else None,
    }


def _get_last_run_summary(db: Session) -> dict[str, Any] | None:
    row = db.query(RunLog).order_by(RunLog.started_at.desc()).first()
    if not row:
        return None
    return {
        "run_id": row.id,
        "status": getattr(row, "status", "unknown"),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "sites_attempted": row.sites_attempted,
        "sites_succeeded": row.sites_succeeded,
        "sites_failed": getattr(row, "sites_failed", 0),
        "jobs_found": getattr(row, "jobs_found", 0),
        "sheet_url": row.sheet_url,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/sites")
def site_health(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(ScraperSite).order_by(ScraperSite.is_default.desc(), ScraperSite.site_name).all()
    return {
        "last_run": _get_last_run_summary(db),
        "sites": [
            {
                "name": row.site_name,
                "last_status": row.last_status,
                "last_job_count": getattr(row, "last_job_count", 0),
                "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
                "consecutive_failures": getattr(row, "consecutive_failures", 0),
                "active": row.is_active,
            }
            for row in rows
        ],
    }
