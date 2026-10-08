import io
import os
import struct
import tempfile
import uuid
import wave
from datetime import datetime, timedelta, timezone
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment before imports
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-chars-long-for-testing"
os.environ["ADMIN_EMAIL"] = "admin@nextaura.io"
os.environ["ADMIN_PASSWORD"] = "test-admin-pass-12345"
os.environ["VOXCPM_PROVIDER"] = "mock"
os.environ["RATE_LIMIT_GENERATE_MAX"] = "100"
os.environ["RATE_LIMIT_LOGIN_MAX"] = "100"
os.environ["RATE_LIMIT_PURCHASE_MAX"] = "100"
os.environ["RATE_LIMIT_ADMIN_MAX"] = "100"

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models.user import User
from app.security.jwt import create_access_token
from app.security.password import hash_password
from app.services.voxcpm import MockVoiceProvider, voice_service

# Use in-memory SQLite database for test isolation
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    # Ensure mock voice provider is used during tests
    voice_service.set_provider(MockVoiceProvider())
    # Reset in-memory rate limiter between tests
    from app.security.rate_limit import get_limiter
    limiter = get_limiter()
    if hasattr(limiter, "_history"):
        limiter._history.clear()
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def regular_user(db_session: Session) -> User:
    user = User(
        email=f"user_{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("Password123!"),
        plan="free",
        is_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def weekly_user(db_session: Session) -> User:
    now = datetime.now(timezone.utc)
    user = User(
        email=f"weekly_{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("Password123!"),
        plan="weekly",
        plan_active_from=now,
        plan_active_until=now + timedelta(days=7),
        is_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def unlimited_user(db_session: Session) -> User:
    now = datetime.now(timezone.utc)
    user = User(
        email=f"unlimited_{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("Password123!"),
        plan="unlimited",
        plan_active_from=now,
        plan_active_until=now + timedelta(days=30),
        is_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session: Session) -> User:
    now = datetime.now(timezone.utc)
    admin = User(
        email="admin@nextaura.io",
        password_hash=hash_password("test-admin-pass-12345"),
        plan="unlimited",
        plan_active_from=now,
        plan_active_until=now + timedelta(days=3650),
        is_admin=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.fixture
def user_token(regular_user: User) -> str:
    return create_access_token(user_id=regular_user.id)


@pytest.fixture
def admin_token(admin_user: User) -> str:
    return create_access_token(user_id=admin_user.id)


def create_mock_wav_bytes(duration_sec: float = 2.0, sample_rate: int = 24000) -> bytes:
    """Generates valid WAV audio bytes for testing."""
    num_samples = int(duration_sec * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        raw_data = struct.pack(f"<{num_samples}h", *([0] * num_samples))
        wf.writeframes(raw_data)
    return buf.getvalue()
