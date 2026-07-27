"""Versioned API router — all platform endpoints mount under /api/v1."""

from fastapi import APIRouter

from office_connect.core.api import audit, auth, config, rbac

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(config.router, tags=["config"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(rbac.router, tags=["rbac"])
api_router.include_router(audit.router, tags=["audit"])
