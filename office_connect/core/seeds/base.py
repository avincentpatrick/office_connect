"""Seed-framework core: the ``SeedDataset`` descriptor.

A dataset is a named, owned, cadence-tagged set of reference rows keyed by a
natural key for **idempotent upsert** (insert new / update changed / skip
unchanged — never duplicate) and **environment-aware** loading.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedDataset:
    name: str
    owner: str  # who keeps it current (named human/role)
    cadence: str  # 'annual' | 'quarterly' | 'on_revision' | 'static' | ...
    environments: tuple[str, ...]  # app_envs it loads in; ('all',) = every env
    model: type
    natural_key: tuple[str, ...]  # columns identifying a row for upsert
    rows: tuple[dict, ...]

    def loads_in(self, app_env: str) -> bool:
        return "all" in self.environments or app_env in self.environments
