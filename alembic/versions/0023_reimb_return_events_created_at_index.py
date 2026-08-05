"""reimb: index reimb_return_events.created_at — the Insights window's predicate

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-05

Stage C Increment R-9 (hardening + the pilot gate). A perf-budget migration:
one index, no data touched, no meaning changed.

``services/insights.py::ranked_reasons`` filters ``reimb_return_events`` on
``created_at`` — twice in one statement, since both the current window and the
prior one are conditional aggregates over the same rows — and the table carried
indexes on ``claim_id`` and ``step_id`` only. Measured on the dev database
before this ran (615 rows in window, 567 live):

    ->  Seq Scan on reimb_return_events ev  (actual time=0.007..0.155 rows=611)
          Filter: (created_at >= (now() - '180 days'::interval))
        Execution Time: 5.188 ms

**The seq scan is currently the right plan, and this index will not be used
today.** That is not an argument against it. The table is append-only and grows
with every returned packet, forever, while the window it is read through stays
fixed at 90 days (``insights.window_days``). So selectivity falls monotonically:
year one reads most of the table, year three reads a slice of it, and the plan
has to flip at some point between. Adding the index now costs one small B-tree
on an append-only table — the cheapest write amplification there is, since
``created_at`` is monotonic so every insert lands on the rightmost leaf — and
means nobody has to notice the day Insights got slow.

Deliberately NOT added: an index on ``reason_ids``. The unnest is a lateral over
rows the ``created_at`` predicate has already reduced, and it is Memoized
(601 hits / 10 misses in the plan above). A GIN index on the JSONB would serve a
"which events cite reason X" query that nothing asks and §9h says nothing should
— the aggregate has no drill-down by design.

Reversible: ``downgrade`` drops the index, restoring ``0022``'s exact schema.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "ix_reimb_return_events_created_at"


def upgrade() -> None:
    op.create_index(INDEX_NAME, "reimb_return_events", ["created_at"])


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="reimb_return_events")
