"""Document generation tasks (Stage C R-5, core-service #8).

WeasyPrint renders in the worker and **never** in the request path — a form takes
seconds, blocks the event loop, and needs the Pango stack. ``core`` may not
import the worker (import-linter), so the Celery task lives here and calls the
pure ``core.documents`` engine through the module's consumer, using the same
async-in-worker discipline as ``ops/attachments_tasks.py`` (fresh NullPool engine
+ ``OCSession`` audit context, disposed in ``finally``).

- ``ops.generate_documents(subject_kind, subject_id)`` — render one subject's
  packet. Idempotent by fingerprint, so a retry or a duplicate enqueue is free.

**Dispatch is polymorphic but the registry is local.** Core hands the task a
``(subject_kind, subject_id)`` pair and nothing more; the mapping from a subject
kind to the consumer that knows how to render it lives here, in ops, which is
allowed to import both. That is what keeps a second consumer (DTWIS, QMS) a
two-line addition rather than a change to core.

Retries follow spec §10 ("Celery task, idempotent, 3 retries"). A render failure
is deliberately NOT fatal to the claim: ``generate_claim_documents`` catches
per-document errors and reports them, so one broken template cannot stop the
other two, and an exhausted retry leaves the item visibly un-generated rather
than storing a corrupt PDF.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

# Registering these installs the OCSession audit + soft-delete listeners.
import office_connect.core.audit  # noqa: F401
import office_connect.core.soft_delete  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from office_connect.core.config import get_settings
from office_connect.core.documents import register_enqueuer
from office_connect.core.session import OCSession, set_audit_context
from office_connect.modules.reimbursement.documents import (
    SUBJECT_KIND as REIMB_SUBJECT_KIND,
)
from office_connect.modules.reimbursement.documents import generate_claim_documents
from office_connect.worker import celery_app

logger = logging.getLogger(__name__)

#: subject_kind → the consumer that renders it. ops is the only layer allowed to
#: know both sides, which is precisely why the dispatch table lives here.
_GENERATORS: dict[str, Callable[[AsyncSession, int], Awaitable[list[Any]]]] = {
    REIMB_SUBJECT_KIND: lambda session, subject_id: generate_claim_documents(
        session, claim_id=subject_id
    ),
}


async def _with_app_session(work, *, request_id: str) -> Any:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        sync_session_class=OCSession,
        expire_on_commit=False,
    )
    try:
        async with factory() as session:
            set_audit_context(session, request_id=request_id)
            result = await work(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


async def _generate(
    session: AsyncSession, subject_kind: str, subject_id: int
) -> dict[str, Any]:
    generator = _GENERATORS.get(subject_kind)
    if generator is None:
        # Not an exception: an unknown subject kind means a consumer enqueued
        # work for a renderer that is not deployed. Retrying cannot fix that, so
        # record it and stop rather than burning three attempts.
        logger.warning(
            "no document generator registered",
            extra={"subject_kind": subject_kind, "subject_id": subject_id},
        )
        return {"subject_kind": subject_kind, "subject_id": subject_id, "results": []}

    results = await generator(session, subject_id)
    return {
        "subject_kind": subject_kind,
        "subject_id": subject_id,
        "results": [
            {
                "document_key": r.document_key,
                "outcome": r.outcome,
                "attachment_id": r.attachment_id,
                "detail": r.detail,
            }
            for r in results
        ],
    }


@celery_app.task(
    name="ops.generate_documents",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
    # A packet is a handful of A4 pages; a minute is generous. The ceiling exists
    # so a pathological template cannot pin a worker slot indefinitely.
    soft_time_limit=120,
    time_limit=180,
)
def generate_documents(self, subject_kind: str, subject_id: int) -> dict[str, Any]:
    payload = asyncio.run(
        _with_app_session(
            lambda s: _generate(s, subject_kind, subject_id),
            request_id="document-generate",
        )
    )
    # Retry only if something actually failed. 'unchanged' and 'generated' are
    # both successes, and retrying a partial success is safe because generation
    # is fingerprint-idempotent — the documents that worked are skipped.
    failed = [r for r in payload["results"] if r["outcome"] == "failed"]
    if failed and self.request.retries < self.max_retries:
        raise self.retry(countdown=60 * (self.request.retries + 1))
    return payload


# ops → core injection (import-linter-legal): the claim lifecycle registers a
# subject to render after commit via this callable. Mirrors the shape of
# attachments_tasks.py and reimbursement_tasks.py.
register_enqueuer(
    lambda subject_kind, subject_id: celery_app.send_task(
        "ops.generate_documents", args=[subject_kind, subject_id]
    )
)
