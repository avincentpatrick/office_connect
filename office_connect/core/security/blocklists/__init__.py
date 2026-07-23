"""Bundled common-password blocklist (NIST SP 800-63B-4 §3.1.1.2 blocklist check).

The runtime makes NO cloud call: the top-100k list is vendored (gzipped) and
loaded once, lazily, into a normalized ``frozenset`` (~90-100k entries after
casefolding, a few MB resident). Source + integrity are recorded in ``README.md``.
"""

from __future__ import annotations

import gzip
from functools import lru_cache
from importlib import resources

_RESOURCE = "top-100000.txt.gz"


@lru_cache(maxsize=1)
def _load() -> frozenset[str]:
    data = (resources.files(__package__) / _RESOURCE).read_bytes()
    text = gzip.decompress(data).decode("utf-8", "ignore")
    return frozenset(
        line.strip().casefold() for line in text.splitlines() if line.strip()
    )


def is_blocklisted(password: str) -> bool:
    """True if the password is in the bundled common-password list (normalized)."""
    return password.strip().casefold() in _load()


def blocklist_size() -> int:
    return len(_load())
