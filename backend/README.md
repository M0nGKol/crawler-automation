# Healthcare Crawler Backend

FastAPI + scraper backend for:
- self-serve onboarding and auth
- Google OAuth + per-user Google Sheets setup
- crawler run pipeline with user-scoped or fallback sheet output

## Prerequisites

- Python 3.11+ (recommended 3.11.x)
- pip

## 1) Install dependencies

From project root:

```bash
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt
```

All `pip` installs should happen inside `backend/venv`.

## 2) Configure environment variables

Copy `backend/.env.example` to `backend/.env`, then fill values:

```bash
cp backend/.env.example backend/.env

# API + auth
NEXTAUTH_SECRET=replace_with_long_random_secret
FRONTEND_URL=http://localhost:3000
# Optional: Neon/Postgres. If not set, backend uses sqlite:///./crawler.db
DATABASE_URL="postgresql://<user>:<password>@<hostname>.neon.tech:<port>/<dbname>?sslmode=require&channel_binding=require"

# Google OAuth (for per-user Sheets onboarding)
GOOGLE_OAUTH_CLIENT_ID=your_google_oauth_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_google_oauth_client_secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/auth/google/callback
GOOGLE_OAUTH_SCOPES="openid email profile https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/drive.file"
TOKEN_ENCRYPTION_KEY=your_fernet_key

# Scraper
ANTHROPIC_API_KEY=
SITES=all
MASKING_LIMIT=30

# Sheets fallback mode (cron/manual without user JWT)
SHEET_DEFAULT=your_default_sheet_id
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
```

Get your connection string from Neon Console -> Project -> Dashboard -> Connect.

### Generate Fernet key

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

## 3) Run backend API (FastAPI)

From project root:

```bash
source backend/venv/bin/activate
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

## 4) Run standalone scraper (no FastAPI required)

From project root:

```bash
source backend/venv/bin/activate
python backend/mvp.py
```

This keeps cron/manual mode working and uses fallback sheet behavior when no user context is provided.

## 5) API routes (used by frontend)

Auth:
- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `GET /auth/google?user_id=...`
- `GET /auth/google/callback`
- `GET /auth/sheets/status`

Pipeline and data:
- `POST /run`
- `GET /status`
- `GET /logs`
- `GET /sites`
- `POST /sites`
- `POST /sites/add-url`
- `PUT /sites/{site_id}`
- `GET /export`
- `GET /health`

### Site source behavior

- Default crawl sources always come from `config/sites.yaml`.
- Each user can add custom sources without losing defaults.
- Runtime merge order is: `default sites` + `user custom sites` (custom keys override defaults if IDs match).

Add one custom source quickly:

```bash
curl -X POST "https://<api-domain>/sites/add-url" \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/jobs",
    "type": "job_board",
    "mode": "claude_fallback",
    "site_id": "example_jobs"
  }'
```

## 6) Matching frontend vars

Frontend `.env.local` should point to this backend:

```bash
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
BACKEND_URL=http://localhost:8000
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
NEXTAUTH_SECRET=replace_with_long_random_secret
NEXTAUTH_URL=http://localhost:3000
```

`NEXTAUTH_SECRET` should match across frontend/backend for consistent JWT behavior.

## 7) Validation commands

From project root:

```bash
python3 -m compileall backend
npm --prefix frontend run build
```

If OAuth popup fails, verify:
- `GOOGLE_OAUTH_REDIRECT_URI` exactly matches Google console config
- `FRONTEND_URL` is correct
- backend is reachable from frontend URLs
- `GET /auth/google/config` output matches your Google Console OAuth settings

## 9) Docker deployment (backend)

The backend folder includes:
- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`

### Build and run with Docker Compose

From project root:

```bash
docker compose -f backend/docker-compose.yml up --build
```

Health check:

```bash
curl http://localhost:8000/health
```

### Run detached

```bash
docker compose -f backend/docker-compose.yml up -d --build
```

### Stop

```bash
docker compose -f backend/docker-compose.yml down
```

### Notes

- Keep secrets in `backend/.env` (already excluded from build context).
- `output/` is mounted so generated files persist across container restarts.
- `config/` is mounted read-only to keep default site config consistent.
- For Neon mode, set `DATABASE_URL` in `backend/.env`.

## 10) Migrate existing `crawler.db` to Neon

Use one of the paths below once Neon `DATABASE_URL` is set in `backend/.env`.

### Option A (recommended): `pgloader`

```bash
pgloader backend/crawler.db "$DATABASE_URL"
```

### Option B: Python migration script (includes row-count checks)

```bash
source backend/venv/bin/activate
python backend/scripts/migrate_sqlite_to_postgres.py
```

The script:
- creates missing tables in Neon using SQLAlchemy models
- copies rows from SQLite to Neon in FK-safe order
- prints source/target row counts for `users`, `run_logs`, `job_hashes`, `scraper_sites`

## 11) Verify and rollback

### Verify

With `DATABASE_URL` set to Neon:
- start backend and call `GET /health`
- test auth flow (`POST /auth/login`)
- test data routes (`GET /logs`, `GET /sites`)
- trigger run route (`POST /run`)

### Rollback

To return to SQLite:
- unset `DATABASE_URL` (or set `DATABASE_URL=sqlite:///./crawler.db`)
- if using Docker and you want file persistence, re-add the `crawler.db` bind mount
- restart backend

## 8) Make Google OAuth public (production)

If users get `Error 403: access_denied`, your app is still in testing mode or the email is not whitelisted.

### A) Temporary unblock with Test users

In Google Cloud Console -> APIs & Services -> OAuth consent screen -> Test users:
- add the client email(s) you want to allow right now
- save and retry login

### B) Publish for all client emails

1. Set OAuth consent screen **Audience** to `External`.
2. Fill app metadata (app name, support email, developer contact email).
3. Add your production domain to **Authorized domains**.
4. Ensure Search Console domain verification is complete for that domain.
5. In Credentials -> OAuth 2.0 Client IDs, add exact production redirect URIs:
   - NextAuth callback: `https://<your-frontend-domain>/api/auth/callback/google`
   - Backend callback: `https://<your-backend-domain>/auth/google/callback`
6. Click **Publish app**.

### C) Verification package (if prompted)

Prepare these ahead of time:
- homepage URL
- privacy policy URL
- terms URL
- scope justification (why Sheets/Drive file access is required)
- short demo video of OAuth flow

### D) Post-publish validation

- test with a Gmail address that is NOT in Test users
- verify login works at `/login`
- verify onboarding Google connect works and returns to `/onboarding/callback?success=true`
