from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Basic health status")
def health():
    settings = get_settings()
    return {
        "ok": True,
        "service": "Next Aura Voice Studio API",
        "environment": settings.ENVIRONMENT,
    }


@router.get("/health/live", summary="Kubernetes / Process Liveness Probe")
def health_live():
    return {"status": "alive"}


@router.get("/health/ready", summary="Readiness Probe (DB connectivity check)")
def health_ready(db: Session = Depends(get_db)):
    try:
        # Check database connectivity
        db.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
        }
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "disconnected",
            },
        )
