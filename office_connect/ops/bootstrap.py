"""Bootstrap CLI — prepare a fresh Office-Connect install (Increment 3).

    docker compose exec app python -m office_connect.ops.bootstrap init
    docker compose exec app python -m office_connect.ops.bootstrap create-admin --email a@b --name "..."
    docker compose exec app python -m office_connect.ops.bootstrap load-fixtures
    docker compose exec app python -m office_connect.ops.bootstrap send-test-email --to a@b

Subcommands:

- ``init``          — ensure the tenant config row + the module feature flags
                      exist (idempotent; safe in any environment).
- ``create-admin``  — record the designated System Admin (email + name) into the
                      tenant's non-public ``settings.bootstrap_admin`` so **Stage
                      B** promotes it to a real user. No ``core_users`` table
                      exists yet — that identity decision is deferred to Stage B
                      (foundation.md §5) — so this records intent, it does not
                      create a login. The record is never served by
                      ``/api/v1/config``.
- ``load-fixtures`` — load synthetic dev fixtures (sample activities). **Hard-
                      refused when APP_ENV=production** (never fabricate data in
                      prod).
- ``send-test-email`` — send a test email through the selected driver (or log in
                      dev) to prove the notification seam is wired.

All DB writes go through the least-privilege ``oc_app`` role via ``OCSession``,
so they are audited (hash chain) exactly like ordinary app writes. Follows the
async-from-sync pattern of ``ops/restore_drill.py`` (a fresh NullPool engine per
command, disposed in ``finally`` — never the app's pooled engine).
"""

import argparse
import asyncio
import json
import sys
from datetime import date
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Importing these registers the OCSession audit + soft-delete listeners so the
# bootstrap writes below are hash-chained and soft-delete-filtered.
import office_connect.core.audit  # noqa: F401
import office_connect.core.soft_delete  # noqa: F401
from office_connect.core.config import Settings, get_settings
from office_connect.core.models import Activity, FeatureFlag, TenantConfig
from office_connect.core.notifications import send_test_email
from office_connect.core.seeds import apply_all
from office_connect.core.session import OCSession, set_audit_context
from office_connect.core.time import utc_now

# Canonical module flags (mirrors migration 0001 seeds — kept in sync on rename).
DEFAULT_FLAGS: tuple[tuple[str, str], ...] = (
    ("module.reimbursement", "Local Travel Reimbursement module"),
    ("module.css_is", "CSS-IS client satisfaction module"),
    ("module.dmwis", "DMWIS document management module"),
)

# Synthetic dev fixtures — clearly non-production sample activities.
_FIXTURE_ACTIVITIES: tuple[dict[str, Any], ...] = (
    {"title": "[fixture] Q1 Health Promotion Planning Workshop",
     "date_start": date(2026, 2, 10), "venue": "BLHSD Conference Room"},
    {"title": "[fixture] Regional Immunization Coverage Review",
     "date_start": date(2026, 3, 5), "venue": "Regional Office"},
    {"title": "[fixture] UHC Integration Site Visit",
     "date_start": date(2026, 4, 18), "venue": "Provincial Health Office"},
)


async def _with_app_session(
    settings: Settings, work: Callable[[AsyncSession], Awaitable[Any]]
) -> Any:
    """Run ``work`` inside an audited ``oc_app`` session on a fresh NullPool
    engine, disposing it afterwards."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        sync_session_class=OCSession,
        expire_on_commit=False,
    )
    try:
        async with factory() as session:
            set_audit_context(session, request_id="bootstrap")
            return await work(session)
    finally:
        await engine.dispose()


# --------------------------------------------------------------------- init
async def _init(session: AsyncSession) -> dict[str, Any]:
    tenant = (
        await session.execute(select(TenantConfig).order_by(TenantConfig.id).limit(1))
    ).scalar_one_or_none()
    created_tenant = False
    if tenant is None:  # safety net — normally seeded by migration 0001
        tenant = TenantConfig(name="Office-Connect", short_name="OC")
        session.add(tenant)
        await session.flush()
        created_tenant = True

    existing_keys = set(
        (await session.execute(select(FeatureFlag.key))).scalars().all()
    )
    created_flags: list[str] = []
    for key, description in DEFAULT_FLAGS:
        if key not in existing_keys:
            session.add(FeatureFlag(key=key, enabled=False, description=description))
            created_flags.append(key)
    await session.commit()
    return {
        "tenant_id": tenant.id,
        "tenant_created": created_tenant,
        "flags_created": created_flags,
        "flags_total": len(existing_keys) + len(created_flags),
    }


# -------------------------------------------------------------- create-admin
async def _record_admin(session: AsyncSession, email: str, name: str) -> dict[str, Any]:
    tenant = (
        await session.execute(select(TenantConfig).order_by(TenantConfig.id).limit(1))
    ).scalar_one_or_none()
    if tenant is None:
        raise RuntimeError("no tenant config found — run 'init' first")
    record = {"email": email, "name": name, "recorded_at": utc_now().isoformat()}
    # Reassign (not in-place mutate) so SQLAlchemy detects the JSONB change.
    tenant.settings = {**(tenant.settings or {}), "bootstrap_admin": record}
    await session.commit()
    return {
        "tenant_id": tenant.id,
        "bootstrap_admin": record,
        "note": "recorded for Stage B promotion; not a login (no user table yet)",
    }


# ------------------------------------------------------------- load-fixtures
async def _load_fixtures(session: AsyncSession) -> dict[str, Any]:
    existing_titles = set(
        (await session.execute(select(Activity.title))).scalars().all()
    )
    created: list[str] = []
    for spec in _FIXTURE_ACTIVITIES:
        if spec["title"] not in existing_titles:
            session.add(Activity(**spec))
            created.append(spec["title"])
    await session.commit()
    total = (
        await session.execute(select(func.count()).select_from(Activity))
    ).scalar_one()
    return {"activities_created": created, "activities_total": total}


# ------------------------------------------------------------ load-reference
async def _load_reference(
    session: AsyncSession, app_env: str, only: set[str] | None
) -> dict[str, Any]:
    """Idempotent, environment-aware upsert of the reference datasets."""
    results = await apply_all(session, app_env=app_env, only=only)
    await session.commit()
    return {"app_env": app_env, "datasets": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="office_connect.ops.bootstrap",
        description="Prepare a fresh Office-Connect install (Increment 3).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="ensure tenant + feature flags exist (idempotent)")
    admin = sub.add_parser(
        "create-admin", help="record the first System Admin (promoted at Stage B)"
    )
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    sub.add_parser(
        "load-fixtures", help="load synthetic dev fixtures (refused in production)"
    )
    ref = sub.add_parser(
        "load-reference",
        help="upsert reference data (idempotent, environment-aware; all envs)",
    )
    ref.add_argument(
        "--dataset", action="append", help="limit to dataset name(s); repeatable"
    )
    mail = sub.add_parser(
        "send-test-email", help="send a test email via the selected driver"
    )
    mail.add_argument("--to", required=True)
    args = parser.parse_args(argv)

    settings = get_settings()

    if args.command == "init":
        result = asyncio.run(_with_app_session(settings, _init))
    elif args.command == "create-admin":
        result = asyncio.run(
            _with_app_session(
                settings, lambda s: _record_admin(s, args.email, args.name)
            )
        )
    elif args.command == "load-fixtures":
        if settings.app_env == "production":
            print(
                "refusing to load fixtures in production (APP_ENV=production)",
                file=sys.stderr,
            )
            return 1
        result = asyncio.run(_with_app_session(settings, _load_fixtures))
    elif args.command == "load-reference":
        only = set(args.dataset) if args.dataset else None
        result = asyncio.run(
            _with_app_session(
                settings, lambda s: _load_reference(s, settings.app_env, only)
            )
        )
    else:  # send-test-email
        result = send_test_email(args.to, settings=settings)

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
