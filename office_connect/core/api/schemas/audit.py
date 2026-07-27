"""Auditor endpoint response models (Stage B / Increment 3, COA Res. 2020-034)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ChainVerifyResponse(BaseModel):
    # "pass" = the hash chain reconstructs from genesis; "fail" = a break was found.
    status: str
    rows_checked: int
    first_broken_row_id: int | None = None
    verified_at: datetime


class AuditRecordEntry(BaseModel):
    id: int
    created_at: datetime
    actor_id: int | None = None
    action: str
    request_id: str | None = None
    old_data: dict[str, Any] | None = None
    new_data: dict[str, Any] | None = None


class AuditRecordTimeline(BaseModel):
    table_name: str
    row_pk: int
    entries: list[AuditRecordEntry]
