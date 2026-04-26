from __future__ import annotations

import json
import os
import re
import secrets
import time
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

# Load .env BEFORE any module that reads os.getenv at import time (e.g. auth.py)
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, HttpUrl
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
from database import RunLog, User, get_db, init_db
from app.config import merge_sites, parse_sites_yaml
from mvp import run_scraper
from onboarding import setup_new_user_workspace

FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
_oauth_states: dict[str, float] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Health Care Crawler API", lifespan=lifespan)

# ── CORS ────────────────────────────────────────────────────────────────
_allowed_origins = [o for o in [
    FRONTEND_URL,
    os.getenv("NEXTAUTH_URL", ""),
    "http://localhost:3000",
] if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
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


def _slugify_site_name(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return slug or f"site_{secrets.token_hex(4)}"


def _default_site_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.replace("www.", "")
    path = parsed.path.strip("/").replace("/", "_")
    return _slugify_site_name(f"{host}_{path}" if path else host)


def _load_default_sites() -> dict[str, Any]:
    with open("config/sites.yaml", encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}
    return loaded.get("sites", {})


def _cleanup_oauth_states() -> None:
    now = time.time()
    for key in list(_oauth_states.keys()):
        if key.startswith("uid_"):
            continue
        if now - _oauth_states[key] > 600:
            _oauth_states.pop(key, None)
            _oauth_states.pop(f"uid_{key}", None)


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
def auth_register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict[str, str]:
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
def auth_google(user_id: str = Query(...), db: Session = Depends(get_db)) -> dict[str, str]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _cleanup_oauth_states()
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    _oauth_states[f"uid_{state}"] = user_id
    return {"auth_url": get_google_auth_url(state)}


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
        _cleanup_oauth_states()
        ts = _oauth_states.get(state)
        if not ts or (time.time() - ts > 600):
            raise ValueError("Invalid or expired state")
        user_id = _oauth_states.get(f"uid_{state}")
        if not user_id:
            raise ValueError("Missing user for OAuth state")

        _oauth_states.pop(state, None)
        _oauth_states.pop(f"uid_{state}", None)

        token = exchange_code_for_token(code)
        _ = get_user_info(token)
        encrypted_token = encrypt_token(token)

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        workspace = await setup_new_user_workspace(
            user=user,
            encrypted_token=encrypted_token,
            company=user.company or user.email,
            db=db,
        )

        url = (
            f"{FRONTEND_URL}/onboarding/callback?success=true"
            f"&sheet_url={urllib.parse.quote(workspace['sheet_url'], safe='')}"
            f"&sheet_title={urllib.parse.quote(workspace['sheet_title'], safe='')}"
        )
        return RedirectResponse(url=url)
    except Exception as exc:
        error = urllib.parse.quote(str(exc), safe="")
        return RedirectResponse(url=f"{FRONTEND_URL}/onboarding/callback?success=false&error={error}")


@app.post("/auth/login")
def auth_login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict[str, str]:
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
def run_pipeline(
    payload: RunRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user: User | None = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()
        user_id = verify_jwt(token)
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
    if not user and payload.user_id:
        user = db.query(User).filter(User.id == payload.user_id).first()

    run_log = RunLog(
        user_id=user.id if user else None,
        started_at=datetime.now(timezone.utc),
        trigger="api",
    )
    db.add(run_log)
    db.commit()
    db.refresh(run_log)

    try:
        result = run_scraper(user_id=user.id if user else None)
        run_log.finished_at = datetime.now(timezone.utc)
        run_log.sites_attempted = result.get("sites_attempted", 0)
        run_log.sites_succeeded = result.get("sites_succeeded", 0)
        run_log.listings_scraped = result.get("count", 0)
        run_log.listings_masked = result.get("count", 0)
        run_log.sheet_url = result.get("sheet_url")
        db.commit()
        return result
    except Exception as exc:
        run_log.finished_at = datetime.now(timezone.utc)
        run_log.errors = str(exc)
        db.commit()
        raise


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
    return {"ok": True, "last_run": last.started_at.isoformat() if last and last.started_at else None}


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
def update_site(
    site_id: str,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = _require_user_from_jwt(authorization, db)
    sites = parse_sites_yaml(user.sites_config)
    sites[site_id] = payload
    user.sites_config = yaml.safe_dump({"sites": sites}, allow_unicode=True)
    db.commit()
    return {"message": "Site updated"}


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
