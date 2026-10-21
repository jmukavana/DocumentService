"""HTTP Basic authentication for document endpoints."""

import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings

basic_auth = HTTPBasic()


async def require_api_key(request: Request,
                          credentials: HTTPBasicCredentials = Depends(basic_auth)) -> str:
    """Return the authenticated key identifier; never expose the secret."""
    if not settings.API_KEY or not settings.API_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="API credentials are not configured")

    key_matches = secrets.compare_digest(
        credentials.username.encode("utf-8"), settings.API_KEY.encode("utf-8")
    )
    secret_matches = secrets.compare_digest(
        credentials.password.encode("utf-8"), settings.API_SECRET.encode("utf-8")
    )
    if not (key_matches and secret_matches):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    request.state.api_key = credentials.username
    return credentials.username
