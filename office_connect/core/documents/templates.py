"""Jinja environment for government-form rendering (core-service #8).

Three decisions worth stating, because each is load-bearing:

**Autoescape is ON, unconditionally.** Every value that reaches a template comes
from claim data a user typed — a purpose line, a destination, a place name. With
autoescape off, a traveller who types ``<script>`` into a purpose field writes
markup into an official government document. It also means the generated PDF is
built from bytes we fully control, which is the whole justification for marking
generated attachments clean without a virus scan (see ``core/attachments``).

**``StrictUndefined``.** A missing context key raises instead of rendering an
empty cell. On a Disbursement Voucher a silently blank amount is far worse than
a failed render: the render failure is visible and retried, the blank is signed.

**No filesystem access from templates.** ``ChoiceLoader`` over the registered
directories only, so a template can never be loaded from a path derived from
user input.

Filters are deliberately few. Money arrives already computed and formatted as a
2-dp string (``core.money.money_str``) — ``money`` only adds the peso sign and
thousands separators, and it accepts strings, so a template physically cannot do
arithmetic. That is standing rule "no client-side money math" applied to print:
the template is a display layer, exactly like the browser.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined
from jinja2.exceptions import TemplateNotFound

from office_connect.core.documents import registry
from office_connect.core.money import money_str
from office_connect.core.time import ensure_aware, to_manila

# The core package's own template directory (base layout, macros).
CORE_TEMPLATE_DIR = Path(__file__).parent / "templates"


def money(value: Decimal | int | str | None) -> str:
    """``6500.00`` → ``₱6,500.00``. Formats only; never computes."""
    if value is None:
        return "—"
    return f"₱{Decimal(money_str(value)):,.2f}"


def manila_date(value: date | datetime | str | None) -> str:
    """A date in the form Philippine government paperwork uses: 03 August 2026."""
    if value is None:
        return "—"
    if isinstance(value, str):
        value = date.fromisoformat(value)
    if isinstance(value, datetime):
        value = to_manila(ensure_aware(value)).date()
    return value.strftime("%d %B %Y")


def manila_datetime(value: datetime | str | None) -> str:
    """A timestamp rendered in Manila time, labelled as such.

    Every generated document carries one of these in its footer. The label is
    not decoration: a PDF that says only "03 August 2026, 4:30 PM" is ambiguous
    in an audit years later, and the database stores UTC.
    """
    if value is None:
        return "—"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return to_manila(ensure_aware(value)).strftime("%d %B %Y, %I:%M %p (Manila)")


def _build_environment() -> Environment:
    search: list[FileSystemLoader] = [FileSystemLoader(str(CORE_TEMPLATE_DIR))]
    search.extend(FileSystemLoader(str(path)) for path in registry.template_dirs())
    env = Environment(
        loader=ChoiceLoader(search),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["money"] = money
    env.filters["manila_date"] = manila_date
    env.filters["manila_datetime"] = manila_datetime
    return env


_environment: Environment | None = None


def get_environment(*, refresh: bool = False) -> Environment:
    """The process-wide environment.

    Cached because building a loader per render is wasteful, but rebuildable:
    ``register_template_dir`` may run after the first render in tests, and a
    stale ChoiceLoader would report a template the registry can see as missing.
    """
    global _environment
    if _environment is None or refresh:
        _environment = _build_environment()
    return _environment


def render_html(template: str, context: dict[str, Any]) -> str:
    """Render one template to an HTML string."""
    try:
        found = get_environment().get_template(template)
    except TemplateNotFound:
        # A module directory registered after the environment was first built is
        # the only benign cause of a miss; rebuild once, then let it raise.
        found = get_environment(refresh=True).get_template(template)
    return found.render(**context)
