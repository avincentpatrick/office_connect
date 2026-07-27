"""Versioned API router — all platform endpoints mount under /api/v1."""

from fastapi import APIRouter

from office_connect.core.api import attachments, audit, auth, config, directory, rbac, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(config.router, tags=["config"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(rbac.router, tags=["rbac"])
api_router.include_router(audit.router, tags=["audit"])
api_router.include_router(attachments.router, tags=["attachments"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(directory.router, tags=["directory"])
