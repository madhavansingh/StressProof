"""
FastAPI authentication dependencies.
"""

from fastapi import Header, HTTPException, status
from .config import settings


async def verify_write_token(authorization: str = Header(None)) -> str:
    """
    Verifies Bearer token for write routes.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Bearer authorization token",
        )
    token = authorization.split("Bearer ")[1].strip()
    if token != settings.API_WRITE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authorization token",
        )
    return token
