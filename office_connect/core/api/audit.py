"""Auditor endpoints (Stage B / Increment 3, COA Res. 2020-034).

A read-only surface for the built-in ``auditor`` role: a printable hash-chain
verification report and a per-record human-readable timeline. Both are gated on
audit permission STRINGS; the ``auditor`` role carries only read/verify grants, so
it is denied every write route platform-wide with no extra mechanism.
"""

from __future__ import annotations

import html

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.api.schemas.audit import (
    AuditRecordEntry,
    AuditRecordTimeline,
    ChainVerifyResponse,
)
from office_connect.core.audit import verify_chain
from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.core.models import AuditLog
from office_connect.core.time import to_manila, utc_now

router = APIRouter()

# The printable report lists at most this many most-recent rows (the whole chain
# is always verified; only the rendered timeline is bounded so the page prints).
_REPORT_TIMELINE_LIMIT = 200


@router.get("/audit/verify")
async def verify_audit_chain(
    request: Request,
    _: Principal = Depends(require_permission("audit.verify")),
    session: AsyncSession = Depends(get_session),
):
    """Verify the whole audit hash chain from genesis. Returns a printable HTML
    report by default, or JSON when the client asks for ``application/json``."""
    rows = (
        await session.execute(select(AuditLog).order_by(AuditLog.id))
    ).scalars().all()
    broken = verify_chain(list(rows))
    verified_at = utc_now()
    result = ChainVerifyResponse(
        status="pass" if broken is None else "fail",
        rows_checked=len(rows),
        first_broken_row_id=broken,
        verified_at=verified_at,
    )
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return result
    return HTMLResponse(_render_report(result, rows[-_REPORT_TIMELINE_LIMIT:]))


@router.get(
    "/audit/records/{table_name}/{row_pk}", response_model=AuditRecordTimeline
)
async def audit_record_timeline(
    table_name: str,
    row_pk: int,
    _: Principal = Depends(require_permission("audit.read")),
    session: AsyncSession = Depends(get_session),
):
    """The ordered change history of one record (a human-readable timeline)."""
    rows = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.table_name == table_name, AuditLog.row_pk == row_pk)
            .order_by(AuditLog.id)
        )
    ).scalars().all()
    if not rows:
        raise APIError(404, "not_found", "No audit history for that record.")
    return AuditRecordTimeline(
        table_name=table_name,
        row_pk=row_pk,
        entries=[
            AuditRecordEntry(
                id=r.id,
                created_at=r.created_at,
                actor_id=r.actor_id,
                action=r.action,
                request_id=r.request_id,
                old_data=r.old_data,
                new_data=r.new_data,
            )
            for r in rows
        ],
    )


def _render_report(result: ChainVerifyResponse, rows: list[AuditLog]) -> str:
    ok = result.status == "pass"
    color = "#0b7a3b" if ok else "#b3261e"  # semantic: green pass / red fail
    verdict = "PASS — chain intact" if ok else "FAIL — chain broken"
    detail = (
        "The audit hash chain reconstructs from genesis with no gaps or tampering."
        if ok
        else f"Verification stopped at audit row id {result.first_broken_row_id}."
    )
    generated = to_manila(result.verified_at).strftime("%Y-%m-%d %H:%M:%S %Z")
    body_rows = "\n".join(
        "<tr>"
        f"<td>{r.id}</td>"
        f"<td>{to_manila(r.created_at).strftime('%Y-%m-%d %H:%M:%S')}</td>"
        f"<td>{html.escape(r.table_name)}</td>"
        f"<td>{r.row_pk if r.row_pk is not None else ''}</td>"
        f"<td>{html.escape(r.action)}</td>"
        f"<td>{r.actor_id if r.actor_id is not None else ''}</td>"
        "</tr>"
        for r in rows
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Audit chain verification report</title>
<style>
  body {{ font-family: system-ui, Arial, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; }}
  .verdict {{ font-size: 1.2rem; font-weight: 700; color: {color};
    border: 2px solid {color}; border-radius: 6px; padding: .6rem 1rem;
    display: inline-block; margin: .5rem 0 1rem; }}
  dl {{ display: grid; grid-template-columns: max-content 1fr; gap: .2rem 1rem; }}
  dt {{ font-weight: 600; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; font-size: .85rem; }}
  th, td {{ border: 1px solid #ccc; padding: .3rem .5rem; text-align: left; }}
  th {{ background: #f2f2f2; }}
  .note {{ color: #555; font-size: .8rem; margin-top: .5rem; }}
  @media print {{ .no-print {{ display: none; }} }}
</style></head>
<body>
  <h1>Office-Connect — Audit Chain Verification Report</h1>
  <div class="verdict">{verdict}</div>
  <dl>
    <dt>Result</dt><dd>{detail}</dd>
    <dt>Rows checked</dt><dd>{result.rows_checked}</dd>
    <dt>Generated</dt><dd>{generated}</dd>
  </dl>
  <h2>Recent audit timeline</h2>
  <table>
    <thead><tr><th>ID</th><th>When (Manila)</th><th>Table</th>
      <th>Row</th><th>Action</th><th>Actor</th></tr></thead>
    <tbody>
    {body_rows}
    </tbody>
  </table>
  <p class="note">Showing the most recent {len(rows)} of {result.rows_checked}
    audit rows. The verdict above reflects the ENTIRE chain from genesis.</p>
</body></html>"""
