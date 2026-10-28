"""
FastAPI application factory and route registration.

State (settings, content store, dataset registry, feed) is created in the lifespan handler,
so importing this module has no filesystem side effects. Run one process
(`uvicorn stressproof_backend.main:app --workers 1`) with DATA_DIR on persistent storage.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.routes import datasets, feed, files, graph, stress
from .config import DEV_WRITE_TOKEN, Settings, check_startup_config, get_settings
from .registry import DatasetRegistry
from .storage.feed import FeedStore
from .storage.store import ContentStore

logger = logging.getLogger("stressproof_backend")


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        check_startup_config(settings)
        db = None
        if settings.storage_backend == "postgres":
            from .storage.postgres import PostgresDatabase, PostgresFeed, PostgresStore
            db = PostgresDatabase(settings.DATABASE_URL, settings.DATABASE_SCHEMA, settings.DATABASE_POOL_MAX)
            await db.open()
            store, feed_store = PostgresStore(db), PostgresFeed(db)
        else:
            store = ContentStore(settings.data_dir)
            feed_store = FeedStore(settings.data_dir / "feed.jsonl")
        await store.open()
        await feed_store.open()
        app.state.settings = settings
        app.state.store = store
        app.state.feed = feed_store
        app.state.registry = DatasetRegistry(settings.datasets_dirs)
        if settings.API_WRITE_TOKEN == DEV_WRITE_TOKEN:
            logger.warning("API_WRITE_TOKEN is the public development default; set a secret before deploying")
        logger.info("storage %s, git commit %s", settings.storage_backend, settings.git_commit)
        try:
            yield
        finally:
            await feed_store.close()
            await store.close()
            if db is not None:
                await db.close()

    app = FastAPI(
        title="StressProof Backend API",
        description="Content-addressed evidence storage, replay execution, and agent feed service.",
        version=__version__,
        lifespan=lifespan,
    )
    # Bearer tokens, no cookies: credentials are not needed, and origins are never wildcarded.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Content-Keccak256"],
    )

    app.include_router(stress.router)
    app.include_router(files.router)
    app.include_router(datasets.router)
    app.include_router(feed.router)
    app.include_router(graph.router)

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {
            "ok": True,
            "service": "stressproof-backend",
            "version": __version__,
            "gitCommit": settings.git_commit,
            "datasets": app.state.registry.ids(),
            "storage": settings.storage_backend,
        }

    return app


app = create_app()
