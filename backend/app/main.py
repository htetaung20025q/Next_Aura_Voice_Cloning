import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from gradio_client import Client, handle_file

load_dotenv()

SPACE = os.getenv("VOXCPM_SPACE", "openbmb/VoxCPM-Demo")
HF_TOKEN = os.getenv("HF_TOKEN", "").strip() or None
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", "12000000"))
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./voice_clone.db")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@nextaura.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")

PLANS = {
    "free": {"name": "Free", "price": 0, "max_words": 500, "weekly_generations": 2, "requires_login": False},
    "weekly": {"name": "Weekly", "price": 25000, "max_words": 5000, "weekly_generations": 6, "requires_login": True},
    "unlimited": {"name": "Unlimited", "price": 50000, "max_words": 5000, "weekly_generations": None, "requires_login": True},
}

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(32), default="free")
    plan_active_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Generation(Base):
    __tablename__ = "generations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    plan: Mapped[str] = mapped_column(String(32))
    word_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    plan: Mapped[str] = mapped_column(String(32))
    payment_reference: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base.metadata.create_all(engine)

def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))
    except Exception:
        return False

bearer = HTTPBearer(auto_error=False)
_client: Optional[Client] = None

app = FastAPI(title="Next Aura Voice API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class AuthIn(BaseModel):
    email: EmailStr
    password: str

class PurchaseIn(BaseModel):
    plan: str
    payment_reference: str


def token_for(user: User) -> str:
    return jwt.encode({"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(days=7)}, SECRET_KEY, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> User:
    if not creds:
        raise HTTPException(401, "Login required.")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=["HS256"])
        uid = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired login.")
    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user:
            raise HTTPException(401, "User not found.")
        return user


def ensure_admin_seed():
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if not existing:
            db.add(User(email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD), is_admin=True))
            db.commit()
ensure_admin_seed()


def active_plan(user: User) -> str:
    if user.plan != "free" and user.plan_active_until and user.plan_active_until < datetime.now(timezone.utc):
        return "free"
    return user.plan


def week_start():
    now = datetime.now(timezone.utc)
    return now - timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)


def word_count(text: str) -> int:
    return len(text.split())


def usage_for(db: Session, user_id: Optional[int]) -> int:
    q = select(Generation).where(Generation.created_at >= week_start())
    if user_id is None:
        q = q.where(Generation.user_id.is_(None))
    else:
        q = q.where(Generation.user_id == user_id)
    return sum(g.word_count for g in db.scalars(q).all())

@app.get("/health")
def health():
    return {"ok": True, "space": SPACE}

@app.get("/api/plans")
def plans():
    return PLANS

@app.post("/api/auth/register")
def register(data: AuthIn):
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == data.email.lower())):
            raise HTTPException(409, "Email is already registered.")
        user = User(email=data.email.lower(), password_hash=hash_password(data.password))
        db.add(user); db.commit(); db.refresh(user)
        return {"token": token_for(user), "user": {"id": user.id, "email": user.email, "plan": "free"}}

@app.post("/api/auth/login")
def login(data: AuthIn):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == data.email.lower()))
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(401, "Invalid email or password.")
        return {"token": token_for(user), "user": {"id": user.id, "email": user.email, "plan": active_plan(user)}}

@app.get("/api/me")
def me(user: User = Depends(current_user)):
    with SessionLocal() as db:
        plan = active_plan(user)
        used = usage_for(db, user.id)
        limit = PLANS[plan]["weekly_generations"]
        return {"id": user.id, "email": user.email, "plan": plan, "used_generations": used, "weekly_generations": limit, "max_words": PLANS[plan]["max_words"], "active_until": user.plan_active_until}

@app.post("/api/purchases")
def purchase(data: PurchaseIn, user: User = Depends(current_user)):
    if data.plan not in ("weekly", "unlimited"):
        raise HTTPException(400, "Premium plan required.")
    with SessionLocal() as db:
        row = PurchaseRequest(user_id=user.id, plan=data.plan, payment_reference=data.payment_reference.strip())
        db.add(row); db.commit(); db.refresh(row)
        return {"ok": True, "request_id": row.id, "status": row.status}

@app.get("/api/admin/purchases")
def admin_purchases(user: User = Depends(current_user)):
    if not user.is_admin: raise HTTPException(403, "Admin only.")
    with SessionLocal() as db:
        rows = db.scalars(select(PurchaseRequest).order_by(PurchaseRequest.created_at.desc())).all()
        return [{"id": r.id, "user_id": r.user_id, "plan": r.plan, "payment_reference": r.payment_reference, "status": r.status, "created_at": r.created_at} for r in rows]

@app.post("/api/admin/purchases/{request_id}/approve")
def approve_purchase(request_id: int, user: User = Depends(current_user)):
    if not user.is_admin: raise HTTPException(403, "Admin only.")
    with SessionLocal() as db:
        r = db.get(PurchaseRequest, request_id)
        if not r: raise HTTPException(404, "Purchase request not found.")
        target = db.get(User, r.user_id)
        target.plan = r.plan
        target.plan_active_until = datetime.now(timezone.utc) + timedelta(days=7) if r.plan == "weekly" else None
        r.status = "approved"
        db.commit()
        return {"ok": True, "user_id": target.id, "plan": target.plan}

@app.post("/api/voice/generate")
async def generate_voice(
    text: str = Form(...), control_instruction: str = Form(""), ultimate_cloning: bool = Form(False), prompt_text: str = Form(""),
    cfg_value: float = Form(2.0), normalize: bool = Form(False), denoise: bool = Form(False), reference_audio: UploadFile | None = File(None),
    authorization: HTTPAuthorizationCredentials = Depends(bearer),
):
    text = text.strip(); wc = word_count(text)
    if not text: raise HTTPException(400, "Text is required.")
    user = None
    if authorization:
        try:
            payload = jwt.decode(authorization.credentials, SECRET_KEY, algorithms=["HS256"]); uid = int(payload["sub"])
            with SessionLocal() as db: user = db.get(User, uid)
        except Exception: user = None
    with SessionLocal() as db:
        plan_name = active_plan(user) if user else "free"
        plan = PLANS[plan_name]
        if wc > plan["max_words"]: raise HTTPException(400, f"Your {plan_name} plan allows up to {plan['max_words']} words per generation.")
        used = usage_for(db, user.id if user else None)
        if plan["weekly_generations"] is not None and used >= plan["weekly_generations"]: raise HTTPException(429, f"Your {plan_name} plan has reached its weekly generation limit.")

    if not 1.0 <= cfg_value <= 3.0: raise HTTPException(400, "CFG value must be between 1.0 and 3.0.")
    if ultimate_cloning and not reference_audio: raise HTTPException(400, "Ultimate cloning requires reference audio.")
    if ultimate_cloning and not prompt_text.strip(): raise HTTPException(400, "Ultimate cloning requires the reference transcript.")

    temp_path = None
    try:
        if reference_audio:
            raw = await reference_audio.read()
            if len(raw) > MAX_AUDIO_BYTES: raise HTTPException(400, "Reference audio is too large.")
            suffix = Path(reference_audio.filename or "reference.wav").suffix or ".wav"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp: tmp.write(raw); temp_path = Path(tmp.name)
        audio_input = handle_file(str(temp_path)) if temp_path else None
        global _client
        if _client is None: _client = Client(SPACE, hf_token=HF_TOKEN)
        result = _client.predict(text, control_instruction, audio_input, ultimate_cloning, prompt_text, float(cfg_value), bool(normalize), bool(denoise), api_name="/generate")
        output_path = result[0] if isinstance(result, tuple) else result
        if isinstance(output_path, dict): output_path = output_path.get("path") or output_path.get("url")
        if not output_path: raise RuntimeError("VoxCPM returned no audio output.")
        with SessionLocal() as db:
            db.add(Generation(user_id=user.id if user else None, plan=plan_name, word_count=wc)); db.commit()
        return FileResponse(output_path, media_type="audio/mpeg", filename="next-aura-voice.mp3", headers={"Cache-Control": "no-store"})
    except HTTPException: raise
    except Exception as exc:
        msg = str(exc)
        if "429" in msg or "busy" in msg.lower(): raise HTTPException(503, "VoxCPM is busy. Please try again in a moment.") from exc
        raise HTTPException(502, f"VoxCPM generation failed: {msg}") from exc
    finally:
        if temp_path: temp_path.unlink(missing_ok=True)
