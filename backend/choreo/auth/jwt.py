from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from choreo.config import settings

_ACCESS_EXPIRE = timedelta(hours=1)
_REFRESH_EXPIRE = timedelta(days=30)


def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + _ACCESS_EXPIRE,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + _REFRESH_EXPIRE,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> str:
    """Verify JWT and return user_id. Raises JWTError on failure."""
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise JWTError("Token missing sub claim")
    return user_id
