"""Versioned API router — all platform endpoints mount under /api/v1."""

from fastapi import APIRouter

from office_connect.core.api import auth, config

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(config.router, tags=["config"])
api_router.include_router(auth.router, tags=["auth"])
