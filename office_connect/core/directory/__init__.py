"""Directory ingestion (core-service #14, Stage B / Increment 4).

The pure landing zone for the decoupled CSS-IS person/org feed. Transport parses
the feed; ``ingest_directory`` upserts it into ``core_org_units`` + ``core_staff``.
"""

from office_connect.core.directory.ingest import (
    DirectoryIngestError,
    IngestResult,
    ingest_directory,
)

__all__ = ["DirectoryIngestError", "IngestResult", "ingest_directory"]
