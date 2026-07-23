"""Seed framework (Increment 4) — idempotent, environment-aware reference data.

``apply_all`` upserts every registered dataset that loads in the current
environment; ``apply_dataset`` does one. Upsert is by natural key: insert new,
update changed, skip unchanged — re-running never duplicates. Loading is audited
(runs through ``OCSession`` in the ops runner). Named owners + cadences live on
each ``SeedDataset`` (``datasets.py``).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.seeds.base import SeedDataset
from office_connect.core.seeds.datasets import REGISTRY

__all__ = ["SeedDataset", "REGISTRY", "apply_dataset", "apply_all", "dataset_names"]


def dataset_names() -> list[str]:
    return [d.name for d in REGISTRY]


async def apply_dataset(session: AsyncSession, dataset: SeedDataset) -> dict[str, Any]:
    """Idempotent upsert of one dataset. Returns a per-dataset summary."""
    inserted = updated = unchanged = 0
    for payload in dataset.rows:
        conds = [
            getattr(dataset.model, key) == payload[key] for key in dataset.natural_key
        ]
        existing = (
            await session.execute(select(dataset.model).where(*conds))
        ).scalar_one_or_none()
        if existing is None:
            session.add(dataset.model(**payload))
            inserted += 1
            continue
        changed = False
        for key, value in payload.items():
            if getattr(existing, key) != value:
                setattr(existing, key, value)
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1
    await session.flush()
    return {
        "dataset": dataset.name,
        "owner": dataset.owner,
        "cadence": dataset.cadence,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
    }


async def apply_all(
    session: AsyncSession, *, app_env: str, only: set[str] | None = None
) -> list[dict[str, Any]]:
    """Upsert every registered dataset eligible for ``app_env`` (optionally
    filtered to ``only`` names). Skipped datasets are reported, not silently
    dropped."""
    results: list[dict[str, Any]] = []
    for dataset in REGISTRY:
        if only and dataset.name not in only:
            continue
        if not dataset.loads_in(app_env):
            results.append({"dataset": dataset.name, "skipped": f"env={app_env}"})
            continue
        results.append(await apply_dataset(session, dataset))
    return results
