"""Calendar composition — master-plan §1.1 #17, api-standards §9k."""

from office_connect.core.calendar.sources import (
    CalendarEvent,
    CalendarSource,
    SourceResult,
    clear_sources,
    register_source,
    registered_sources,
)

__all__ = [
    "CalendarEvent",
    "CalendarSource",
    "SourceResult",
    "clear_sources",
    "register_source",
    "registered_sources",
]
