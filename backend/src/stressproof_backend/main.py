"""
FastAPI application factory and route registration.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .api.routes import datasets, feed, files, graph, stress

app = FastAPI(
    title="StressProof Backend API",
    description="Content-addressed evidence storage, replay execution, and agent feed service.",
    version="0.1.0",
)

# CORS Middleware
origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
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
        "version": "0.1.0",
    }
