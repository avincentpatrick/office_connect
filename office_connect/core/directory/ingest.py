"""Directory ingestion service (Stage B / Increment 4).

CSS-IS is a separate system that *feeds* person/org data in for display —
decoupled by decision (foundation §5/§7 B1): no code dependency, no live link.
This is the pure core service that lands a **parsed** feed into
``core_org_units`` + ``core_staff``: an idempotent upsert keyed by org-unit
``code`` and staff ``employee_no``, restoring soft-deleted rows on reappearance.

Transport (the ops ``ingest-directory`` CLI and ``POST /api/v1/directory/import``)
parses the CSV/JSON and hands this service ``Sequence[Mapping]`` — so the feed
*format* stays decoupled from the logic. It runs on the caller's ``OCSession`` so
every write is hash-chained + soft-delete-aware; ``core`` imports no ops/worker/Redis.

The whole feed is validated in memory first (parents resolvable, no cycles, known
kinds, division/section point at the right kind, no duplicate keys) and applied
atomically — a bad feed raises ``DirectoryIngestError`` and commits nothing (the
caller owns the transaction/commit).

Absence policy: default **leave-alone** — a truncated feed never wipes the
directory. ``deactivate_absent=True`` (prune) soft-deletes live staff absent from
the feed (guarded against an empty feed) and returns the linked user ids for a
caller that holds ``SessionStore`` to offboard; this service stays Redis-free.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import OrgUnit, Staff, User
from office_connect.core.session import set_audit_context
from office_connect.core.soft_delete import soft_delete

_ORG_KINDS = frozenset({"office", "division", "section", "unit"})
_MAX_TREE_DEPTH = 64  # cycle/pathological-depth guard for the parent walk


class DirectoryIngestError(RuntimeError):
    """The feed failed validation — nothing was committed."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class IngestResult:
    org_units_created: list[str] = field(default_factory=list)
    org_units_updated: list[str] = field(default_factory=list)
    org_units_restored: list[str] = field(default_factory=list)
    staff_created: list[str] = field(default_factory=list)
    staff_updated: list[str] = field(default_factory=list)
    staff_restored: list[str] = field(default_factory=list)
    staff_deactivated: list[str] = field(default_factory=list)
    deactivated_user_ids: list[int] = field(default_factory=list)


def _norm(value: object) -> str | None:
    """Trim and coalesce empty strings to None (empty cell = absent)."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


async def ingest_directory(
    session: AsyncSession,
    *,
    org_units: Sequence[Mapping],
    staff: Sequence[Mapping],
    actor_id: int | None = None,
    request_id: str | None = None,
    deactivate_absent: bool = False,
) -> IngestResult:
    if actor_id is not None or request_id is not None:
        set_audit_context(session, actor_id=actor_id, request_id=request_id)

    result = IngestResult()
    errors: list[str] = []

    # ---- normalize + validate the org-unit batch ---------------------------
    org_specs: dict[str, dict] = {}
    for i, raw in enumerate(org_units):
        code = _norm(raw.get("code"))
        if code is None:
            errors.append(f"org_units[{i}]: missing code")
            continue
        if code in org_specs:
            errors.append(f"org_units: duplicate code {code!r}")
            continue
        kind = _norm(raw.get("kind"))
        if kind not in _ORG_KINDS:
            errors.append(f"org_units[{code}]: invalid kind {kind!r}")
        org_specs[code] = {
            "code": code,
            "name": _norm(raw.get("name")),
            "kind": kind,
            "parent_code": _norm(raw.get("parent_code")),
            "sort_order": int(raw.get("sort_order") or 0),
            "is_active": _as_bool(raw.get("is_active"), default=True),
        }
        if org_specs[code]["name"] is None:
            errors.append(f"org_units[{code}]: missing name")

    existing_org = {
        ou.code: ou
        for ou in (
            (
                await session.execute(
                    select(OrgUnit).execution_options(include_deleted=True)
                )
            )
            .scalars()
            .all()
        )
    }

    # Parent references must resolve (in the feed or already in the DB) and the
    # feed's own parent graph must be acyclic.
    for code, spec in org_specs.items():
        parent = spec["parent_code"]
        if parent is None:
            continue
        if parent not in org_specs and parent not in existing_org:
            errors.append(f"org_units[{code}]: unknown parent_code {parent!r}")
    errors.extend(_detect_org_cycles(org_specs))

    # ---- normalize + validate the staff batch ------------------------------
    staff_specs: list[dict] = []
    seen_emp: set[str] = set()
    seen_email: set[str] = set()
    for i, raw in enumerate(staff):
        emp = _norm(raw.get("employee_no"))
        if emp is None:
            errors.append(f"staff[{i}]: missing employee_no")
            continue
        if emp in seen_emp:
            errors.append(f"staff: duplicate employee_no {emp!r}")
            continue
        seen_emp.add(emp)
        given = _norm(raw.get("given_name"))
        surname = _norm(raw.get("surname"))
        if given is None or surname is None:
            errors.append(f"staff[{emp}]: given_name and surname are required")
        email = _norm(raw.get("email"))
        if email is not None:
            if email.lower() in seen_email:
                errors.append(f"staff: duplicate email {email!r}")
            seen_email.add(email.lower())
        full_name = _norm(raw.get("full_name")) or (
            f"{given} {surname}" if given and surname else None
        )
        staff_specs.append(
            {
                "employee_no": emp,
                "given_name": given,
                "middle_name": _norm(raw.get("middle_name")),
                "surname": surname,
                "full_name": full_name,
                "email": email,
                "position_title": _norm(raw.get("position_title")),
                "plantilla_item_no": _norm(raw.get("plantilla_item_no")),
                "employment_status": _norm(raw.get("employment_status")),
                "division_code": _norm(raw.get("division_code")),
                "section_code": _norm(raw.get("section_code")),
            }
        )

    # Staff division/section codes must name a unit (in the feed or the DB) of the
    # right kind — validated upfront (against the post-ingest kind) so a bad feed
    # flushes nothing.
    kind_by_code = {code: spec["kind"] for code, spec in org_specs.items()}
    for code, ou in existing_org.items():
        kind_by_code.setdefault(code, ou.kind)
    for spec in staff_specs:
        for field_name, want_kind in (
            ("division_code", "division"),
            ("section_code", "section"),
        ):
            code = spec[field_name]
            if code is None:
                continue
            kind = kind_by_code.get(code)
            if kind is None:
                errors.append(
                    f"staff[{spec['employee_no']}]: unknown {field_name} {code!r}"
                )
            elif kind != want_kind:
                errors.append(
                    f"staff[{spec['employee_no']}]: {field_name} {code!r} "
                    f"is a {kind}, expected {want_kind}"
                )

    if errors:
        raise DirectoryIngestError(errors)

    # ---- apply org units (topological: parents before children) ------------
    code_to_unit: dict[str, OrgUnit] = dict(existing_org)
    for code in _topological_order(org_specs):
        spec = org_specs[code]
        parent_id = (
            code_to_unit[spec["parent_code"]].id if spec["parent_code"] else None
        )
        row = existing_org.get(code)
        if row is None:
            row = OrgUnit(
                code=code,
                name=spec["name"],
                kind=spec["kind"],
                parent_org_unit_id=parent_id,
                sort_order=spec["sort_order"],
                is_active=spec["is_active"],
            )
            session.add(row)
            await session.flush()
            code_to_unit[code] = row
            result.org_units_created.append(code)
        else:
            restored = row.deleted_at is not None
            if restored:
                row.deleted_at = None
                row.deleted_by = None
            row.name = spec["name"]
            row.kind = spec["kind"]
            row.parent_org_unit_id = parent_id
            row.sort_order = spec["sort_order"]
            row.is_active = spec["is_active"]
            await session.flush()
            code_to_unit[code] = row
            (result.org_units_restored if restored else result.org_units_updated).append(
                code
            )

    # ---- apply staff -------------------------------------------------------
    existing_staff = {
        s.employee_no: s
        for s in (
            (
                await session.execute(
                    select(Staff).execution_options(include_deleted=True)
                )
            )
            .scalars()
            .all()
        )
    }
    for spec in staff_specs:
        div = code_to_unit.get(spec["division_code"]) if spec["division_code"] else None
        sec = code_to_unit.get(spec["section_code"]) if spec["section_code"] else None
        row = existing_staff.get(spec["employee_no"])
        fields = {
            "given_name": spec["given_name"],
            "middle_name": spec["middle_name"],
            "surname": spec["surname"],
            "full_name": spec["full_name"],
            "email": spec["email"],
            "position_title": spec["position_title"],
            "plantilla_item_no": spec["plantilla_item_no"],
            "employment_status": spec["employment_status"],
            "division_id": div.id if div else None,
            "section_id": sec.id if sec else None,
        }
        if row is None:
            session.add(Staff(employee_no=spec["employee_no"], **fields))
            result.staff_created.append(spec["employee_no"])
        else:
            restored = row.deleted_at is not None
            if restored:
                row.deleted_at = None
                row.deleted_by = None
            for key, value in fields.items():
                setattr(row, key, value)
            (result.staff_restored if restored else result.staff_updated).append(
                spec["employee_no"]
            )
    await session.flush()

    # ---- optional prune (OFF by default; empty-feed guarded) ---------------
    if deactivate_absent:
        if not staff_specs:
            raise DirectoryIngestError(
                ["refusing to prune the directory against an empty staff feed"]
            )
        feed_emps = {s["employee_no"] for s in staff_specs}
        for emp, row in existing_staff.items():
            if emp not in feed_emps and row.deleted_at is None:
                soft_delete(row, actor_id=actor_id)
                result.staff_deactivated.append(emp)
                linked = (
                    (
                        await session.execute(
                            select(User.id).where(User.staff_id == row.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                result.deactivated_user_ids.extend(linked)
        await session.flush()

    return result


def _as_bool(value: object, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "t", "yes", "y")


def _detect_org_cycles(specs: dict[str, dict]) -> list[str]:
    """Report any org-unit whose parent chain (within the feed) loops."""
    errors: list[str] = []
    for code in specs:
        seen = set()
        cur = code
        depth = 0
        while cur is not None and cur in specs:
            if cur in seen or depth > _MAX_TREE_DEPTH:
                errors.append(f"org_units[{code}]: parent cycle detected")
                break
            seen.add(cur)
            cur = specs[cur]["parent_code"]
            depth += 1
    return errors


def _topological_order(specs: dict[str, dict]) -> list[str]:
    """Codes ordered so a node's in-feed parent precedes it (Kahn); nodes whose
    parent is absent from the feed (already in the DB, or a root) come first."""
    order: list[str] = []
    placed: set[str] = set()
    remaining = dict(specs)
    while remaining:
        ready = [
            code
            for code, spec in remaining.items()
            if spec["parent_code"] not in remaining
        ]
        # Deterministic order; validation already guaranteed no cycle so `ready`
        # is non-empty here.
        for code in sorted(ready):
            order.append(code)
            placed.add(code)
            del remaining[code]
    return order
