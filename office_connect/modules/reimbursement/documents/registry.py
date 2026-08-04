"""Register the module's forms with core-service #8 (R-5).

Importing this module is what teaches core that ``reimb.iot45`` exists and which
template renders it. Core never imports reimbursement — the dependency points
one way only, which is what keeps `lint-imports` green.

The specs here are the **code-side** half. Which checklist code each document
satisfies, and whether it is currently issued, is data (``reimb_template_maps``,
seeded) so the R-9 catalog editor can retire a form when a circular is
superseded without a deployment.
"""

from __future__ import annotations

from pathlib import Path

from office_connect.core.documents import DocumentSpec, register_document
from office_connect.core.documents import register_template_dir

TEMPLATE_DIR = Path(__file__).parent / "templates"

#: Namespaced keys — a bare form number would collide across modules.
IOT_45 = "reimb.iot45"
AR_01 = "reimb.ar01"
DV_32 = "reimb.dv32"

SPECS = (
    DocumentSpec(
        key=IOT_45,
        template="iot45.html.j2",
        title="Itinerary of Travel",
    ),
    DocumentSpec(
        key=AR_01,
        template="ar01.html.j2",
        title="Accomplishment Report",
    ),
    DocumentSpec(
        key=DV_32,
        template="dv32.html.j2",
        title="Disbursement Voucher",
    ),
)


def register() -> None:
    """Idempotent — safe to call from module import and again from a test."""
    register_template_dir(TEMPLATE_DIR)
    for spec in SPECS:
        register_document(spec)


register()
