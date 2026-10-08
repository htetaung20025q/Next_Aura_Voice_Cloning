from datetime import datetime, timezone
from typing import Generator, Optional
from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.security.anonymous import (
    generate_signed_anonymous_token,
    get_ip_abuse_hash,
    verify_and_extract_anonymous_id,
)
from app.security.jwt import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_token_from_request(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    cookie_token: Optional[str] = Cookie(None, alias="access_token"),
) -> Optional[str]:
    """
    Extracts JWT access token from either:
    1. 'Authorization: Bearer <token>' HTTP Header
    2. 'access_token' HttpOnly Cookie
    """
    if bearer and bearer.credentials:
        return bearer.credentials
    if cookie_token:
        return cookie_token
    return None


def get_current_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(get_token_from_request),
) -> User:
    """
    Authenticates the current user via JWT.
    Raises HTTP 401 if token is missing, invalid, or expired.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication session.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user account is locked
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked due to repeated failed login attempts. Please try again later.",
        )

    return user


def get_optional_current_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(get_token_from_request),
) -> Optional[User]:
    """
    Extracts authenticated user if valid credentials are provided, but allows unauthenticated visitors.
    """
    if not token:
        return None

    user_id = decode_access_token(token)
    if not user_id:
        return None

    user = db.get(User, user_id)
    if not user:
        return None

    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        return None

    return user


def get_current_active_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Strict authorization dependency ensuring the authenticated user possesses admin privileges.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required to access this resource.",
        )
    return current_user


class AnonymousSession:
    def __init__(self, anon_id: str, ip_hash: str, is_new: bool = False, cookie_to_set: Optional[str] = None):
        self.anon_id = anon_id
        self.ip_hash = ip_hash
        self.is_new = is_new
        self.cookie_to_set = cookie_to_set


def get_anonymous_session(
    request: Request,
    response: Response,
    anon_cookie: Optional[str] = Cookie(None, alias="na_anon_session"),
) -> AnonymousSession:
    """
    Resolves or issues a cryptographically signed anonymous session cookie and IP abuse hash.
    """
    settings = get_settings()
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "127.0.0.1")
    )
    ip_hash = get_ip_abuse_hash(client_ip)

    anon_id = verify_and_extract_anonymous_id(anon_cookie)
    if anon_id:
        return AnonymousSession(anon_id=anon_id, ip_hash=ip_hash, is_new=False)

    # Generate new signed token
    new_token = generate_signed_anonymous_token()
    extracted_id = verify_and_extract_anonymous_id(new_token) or "anonymous"

    # Attach signed cookie to response
    response.set_cookie(
        key=settings.ANONYMOUS_COOKIE_NAME,
        value=new_token,
        max_age=60 * 60 * 24 * 30,  # 30 days
        httponly=True,
        secure=bool(settings.COOKIE_SECURE),
        samesite=settings.COOKIE_SAMESITE,
    )

    return AnonymousSession(anon_id=extracted_id, ip_hash=ip_hash, is_new=True, cookie_to_set=new_token)
