"""
FastAPI dependencies: shared app state (created in the lifespan handler) and write auth.
"""

import hmac

from fastapi import Header, HTTPException, Request, status

from .config import Settings
from .registry import DatasetRegistry
from .storage.feed import FeedStore
from .storage.store import ContentStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> ContentStore:
    return request.app.state.store


def get_registry(request: Request) -> DatasetRegistry:
    return request.app.state.registry


def get_feed(request: Request) -> FeedStore:
    return request.app.state.feed


async def verify_write_token(request: Request, authorization: str = Header(None)) -> str:
    """Bearer token for write routes: 401 when missing or malformed, 403 when wrong."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Bearer authorization token",
        )
    token = authorization[len("Bearer "):].strip()
    expected = request.app.state.settings.API_WRITE_TOKEN
    if not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authorization token",
        )
    return token
