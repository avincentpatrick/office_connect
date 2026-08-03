"""Checklist-engine error codes — thin wrappers over the app's ``APIError``.

Same pattern as ``core/workflow/errors.py``. These are **authoring-time** errors
only: they fire when a catalog row's ``required_rule`` / ``auto_checks`` JSONB is
malformed, which is a seed/admin-editor problem, never a claimant one. The
*evaluation* path never raises (see ``grammar.evaluate_required_rule``).
"""

from __future__ import annotations

from office_connect.core.api.errors import APIError


def invalid_rule(detail: str) -> APIError:
    return APIError(
        422,
        "checklist_invalid_rule",
        f"The checklist requirement rule is not valid: {detail}",
    )


def unknown_rule_operator(operator: str) -> APIError:
    return APIError(
        422,
        "checklist_unknown_rule_operator",
        f"'{operator}' is not a checklist rule operator "
        "(allowed: always, if, any, all).",
    )


def unknown_comparator(comparator: str) -> APIError:
    return APIError(
        422,
        "checklist_unknown_comparator",
        f"'{comparator}' is not a checklist comparator (allowed: eq, contains, gt).",
    )


def invalid_auto_check(detail: str) -> APIError:
    return APIError(
        422,
        "checklist_invalid_auto_check",
        f"The checklist auto-check is not valid: {detail}",
    )


def unknown_check_type(check_type: str) -> APIError:
    return APIError(
        422,
        "checklist_unknown_check_type",
        f"'{check_type}' is not a known auto-check type.",
    )
