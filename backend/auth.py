from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import bcrypt
import gspread
import requests
from cryptography.fernet import Fernet
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from jose import JWTError, jwt
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
TOKEN_ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY", "")
JWT_SECRET = os.getenv("NEXTAUTH_SECRET", "")
JWT_ALGORITHM = "HS256"

DEFAULT_GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
GOOGLE_SCOPES = [
    scope.strip()
    for scope in os.getenv("GOOGLE_OAUTH_SCOPES", " ".join(DEFAULT_GOOGLE_SCOPES)).split()
    if scope.strip()
]


def _get_cipher() -> Fernet:
    if TOKEN_ENCRYPTION_KEY:
        return Fernet(TOKEN_ENCRYPTION_KEY.encode())
    fallback = base64.urlsafe_b64encode(b"local-dev-token-key".ljust(32, b"_"))
    return Fernet(fallback)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def get_google_auth_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


def exchange_code_for_token(code: str) -> dict[str, Any]:
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def get_user_info(token: dict[str, Any]) -> dict[str, Any]:
    resp = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {token['access_token']}"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def encrypt_token(token: dict[str, Any]) -> str:
    return _get_cipher().encrypt(json.dumps(token).encode()).decode()


def decrypt_token(encrypted: str) -> dict[str, Any]:
    return json.loads(_get_cipher().decrypt(encrypted.encode()).decode())


def get_google_sheets_client(encrypted_token: str) -> gspread.Client:
    token = decrypt_token(encrypted_token)
    creds = Credentials(
        token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_OAUTH_CLIENT_ID,
        client_secret=GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=GOOGLE_SCOPES,
    )
    if not creds.valid and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
    return gspread.authorize(creds)


def create_jwt(user_id: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    payload = {"sub": user_id, "exp": expires}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> str | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")
