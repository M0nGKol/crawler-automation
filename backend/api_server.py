from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from auth import create_access_token, get_oauth_redirect_url
from database import SessionLocal, init_db
from mvp import run_scraper
from onboarding import setup_user_sheet

app = FastAPI(title="Health Care Crawler API")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class OnboardingRequest(BaseModel):
    email: EmailStr
    sheet_id: str


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    Path("output").mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/auth/google")
def auth_google() -> dict:
    return {"redirect_url": get_oauth_redirect_url("google")}


@app.post("/auth/token")
def auth_token(email: EmailStr) -> dict:
    token = create_access_token(subject=str(email))
    return {"access_token": token, "token_type": "bearer"}


@app.post("/onboarding")
def onboarding(payload: OnboardingRequest, db: Session = Depends(get_db)) -> dict:
    user = setup_user_sheet(db=db, user_email=str(payload.email), sheet_id=payload.sheet_id)
    return {"user_id": user.id, "email": user.email, "sheet_id": user.sheet_id}


@app.post("/run")
def run() -> dict:
    result = run_scraper()
    if not result:
        raise HTTPException(status_code=500, detail="Scraper returned empty result.")
    return result
