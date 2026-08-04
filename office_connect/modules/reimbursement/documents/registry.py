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

#: The combined printable packet (R-5-packet). Deliberately NOT in
#: ``reimb_template_maps``: it satisfies no checklist code, because no COA
#: circular names the folder its documents travel in. It is a claim-level
#: artifact, generated beside the bindings rather than from one — see the module
#: doc's delta register.
PACKET = "reimb.packet"

#: The packet's own heading and filename stem. A constant rather than a seeded
#: binding row for the same reason: nothing about it is per-circular
#: configuration, so a row in a table the R-9 editor manages would invite an
#: edit that means nothing.
PACKET_TITLE = "Travel claim packet"

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
    DocumentSpec(
        key=PACKET,
        template="packet.html.j2",
        title=PACKET_TITLE,
    ),
)

#: document key → the body partial the packet embeds for it.
#:
#: A **code-side** table, never data. The packet template includes
#: ``section.body``, and a dynamic ``{% include %}`` is only safe while its value
#: cannot be influenced by input — so the name is resolved from this frozen dict
#: and a key that is absent is listed on the cover but not embedded, rather than
#: reaching the loader. (``reimb_template_maps.document_key`` is admin-editable
#: data; deriving a template path from it would hand the R-9 catalog editor a
#: template-injection surface.)
BODY_PARTIALS = {
    IOT_45: "_iot45_body.html.j2",
    AR_01: "_ar01_body.html.j2",
    DV_32: "_dv32_body.html.j2",
}


def register() -> None:
    """Idempotent — safe to call from module import and again from a test."""
    register_template_dir(TEMPLATE_DIR)
    for spec in SPECS:
        register_document(spec)


register()
