# Healthcare Crawler Frontend

Next.js App Router frontend for:
- self-serve onboarding (`/onboarding`)
- login (`/login`)
- dashboard/config/logs/users pages
- backend API integration (FastAPI)

## Prerequisites

- Node.js 20+
- npm 10+
- Running backend API (`backend/main.py`) on Railway or locally

## 1) Install dependencies

From project root:

```bash
npm --prefix frontend install
```

## 2) Configure environment variables

Copy `frontend/.env.example` to `frontend/.env.local`, then fill values:

```bash
cp frontend/.env.example frontend/.env.local

NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
BACKEND_URL=http://localhost:8000

GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret

NEXTAUTH_SECRET=replace_with_long_random_secret
NEXTAUTH_URL=http://localhost:3000
```

### Variable notes

- `NEXT_PUBLIC_BACKEND_URL`: used by browser-side frontend API calls.
- `BACKEND_URL`: used by server-side route handlers.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: used by NextAuth Google provider.
- `NEXTAUTH_SECRET`: session/JWT secret for NextAuth.
- `NEXTAUTH_URL`: frontend base URL.

For production, set:
- `NEXTAUTH_URL=https://<your-frontend-domain>`
- same `GOOGLE_CLIENT_ID` as backend `GOOGLE_OAUTH_CLIENT_ID`
- redirect URI in Google console: `https://<your-frontend-domain>/api/auth/callback/google`

## 3) Run the app

From project root:

```bash
npm --prefix frontend run dev
```

Open [http://localhost:3000](http://localhost:3000)

## 4) Run production build check

```bash
npm --prefix frontend run build
```

## 5) Typical flow to test

1. Go to `/onboarding`
2. Create account
3. Connect Google in popup
4. Complete setup
5. Go to `/dashboard`
6. Login later via `/login`

## Backend requirement reminder

This frontend expects backend routes from `backend/main.py`, including:
- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `GET /auth/google`
- `GET /auth/google/callback`
- `GET /auth/sheets/status`
- `POST /run`
- `GET /status`
- `GET /logs`
- `GET /sites`
- `GET /health`

If frontend pages fail, verify backend is running and `NEXT_PUBLIC_BACKEND_URL` / `BACKEND_URL` match it.

## OAuth 403 quick fix

If a client email sees `Error 403: access_denied`:
- add that email in Google OAuth consent screen -> **Test users** (temporary)
- publish OAuth app to production with **External** audience for full public access
