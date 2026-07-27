"""Workflow engine error codes — thin wrappers over the app's ``APIError``.

Stable ``code`` slugs a consumer (or the future HTTP router) branches on. Reusing
``APIError`` means these surface through the existing structured-error envelope with
the right HTTP status, exactly like ``maker_checker.assert_segregation``.
"""

from __future__ import annotations

from office_connect.core.api.errors import APIError


def instance_not_found() -> APIError:
    return APIError(404, "workflow_instance_not_found", "Workflow instance not found.")


def definition_not_published(code: str) -> APIError:
    return APIError(
        409,
        "workflow_definition_not_published",
        f"No published version of workflow '{code}'.",
    )


def module_disabled(flag_key: str) -> APIError:
    return APIError(
        409,
        "workflow_module_disabled",
        "This workflow is disabled; no new items can be started.",
    )


def stale_version() -> APIError:
    return APIError(
        409,
        "stale_workflow_version",
        "This item changed since you loaded it — reload and try again.",
    )


def state_conflict() -> APIError:
    return APIError(
        409,
        "workflow_state_conflict",
        "This item already moved on — someone acted first.",
    )


def already_acted() -> APIError:
    return APIError(
        409, "workflow_step_already_acted", "You have already acted on this step."
    )


def not_authorized() -> APIError:
    return APIError(403, "workflow_not_authorized", "You may not take this action.")


def transition_not_allowed(action: str) -> APIError:
    return APIError(
        422,
        "workflow_transition_not_allowed",
        f"'{action}' is not allowed from the current state.",
    )


def comment_required() -> APIError:
    return APIError(
        422, "workflow_comment_required", "A reason is required for this action."
    )


def invalid_definition(message: str) -> APIError:
    return APIError(400, "workflow_invalid_definition", message)


def already_published() -> APIError:
    return APIError(
        409, "workflow_version_published", "A published version cannot be edited."
    )
