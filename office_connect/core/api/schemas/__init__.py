"""Pydantic request/response schemas for the HTTP API.

Kept separate from the SQLAlchemy ORM models (``core/models``): these describe the
wire contract (api-standards §2), the ORM describes the database. The first
schemas land with auth (Stage B / Increment 2); modules add their own here.
"""
