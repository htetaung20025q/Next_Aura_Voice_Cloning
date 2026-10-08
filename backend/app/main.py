import logging
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api import (
    admin_router,
    auth_router,
    health_router,
    purchases_router,
    voice_router,
)
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.middleware import (
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    StructuredLoggingMiddleware,
)
from app.models.user import User
from app.security.password import hash_password, verify_password

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s (%(process)d): %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("next_aura.main")


def ensure_admin_seed():
    """
    Creates or validates initial administrator account at startup.
    Ensures password hash and unlimited plan stay synchronized with settings.
    """
    settings = get_settings()
    with SessionLocal() as db:
        admin_email = settings.ADMIN_EMAIL.lower().strip()
        existing = db.scalar(select(User).where(User.email == admin_email))
        if not existing:
            logger.info("Seeding initial administrator account: %s", admin_email)
            admin_user = User(
                email=admin_email,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                is_admin=True,
                plan="unlimited",
            )
            db.add(admin_user)
            db.commit()
        else:
            changed = False
            if not existing.is_admin:
                existing.is_admin = True
                changed = True
            if existing.plan != "unlimited":
                existing.plan = "unlimited"
                changed = True
            if not verify_password(settings.ADMIN_PASSWORD, existing.password_hash):
                existing.password_hash = hash_password(settings.ADMIN_PASSWORD)
                existing.failed_login_attempts = 0
                existing.locked_until = None
                changed = True
            if changed:
                db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup validation
    settings = get_settings()
    logger.info("Initializing Next Aura Voice Studio Backend [Environment=%s]", settings.ENVIRONMENT)

    if settings.ENVIRONMENT != "test":
        # Initialize tables (fallback safety for fresh environments)
        Base.metadata.create_all(bind=engine)

        # Seed Admin
        ensure_admin_seed()

    yield

    logger.info("Shutting down Next Aura Voice Studio Backend")


settings = get_settings()

app = FastAPI(
    title="Next Aura Voice Studio API",
    description="High-performance, secure backend for VoxCPM AI voice cloning and subscription management.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# 1. Request ID Middleware
app.add_middleware(RequestIDMiddleware)

# 2. Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# 3. Structured Logging Middleware
app.add_middleware(StructuredLoggingMiddleware)

# 4. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-ID",
        "Content-Disposition",
        "X-Audio-Id",
        "X-Generation-Id",
        "X-Preset-Id",
        "X-Preset-Name",
        "X-Category",
        "X-Intensity",
        "X-Processing-Time-Ms",
        "X-Cached",
        "X-Styled-Audio",
    ],
)

# Register Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(voice_router)
app.include_router(purchases_router)
app.include_router(admin_router)


# Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", None)
    errors = []
    for err in exc.errors():
        field = " -> ".join(str(loc) for loc in err.get("loc", []))
        msg = err.get("msg", "Invalid input")
        errors.append(f"{field}: {msg}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT if hasattr(status, "HTTP_422_UNPROCESSABLE_CONTENT") else 422,
        content={
            "detail": errors[0] if len(errors) == 1 else errors,
            "request_id": req_id,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    req_id = getattr(request.state, "request_id", None)
    headers = exc.headers or {}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": req_id,
        },
        headers=headers,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", None)
    logger.error("Unhandled server exception (req_id=%s): %s", req_id, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred. Please try again later.",
            "request_id": req_id,
        },
    )
