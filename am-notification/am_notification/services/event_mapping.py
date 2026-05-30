from __future__ import annotations

from typing import Any

EVENT_TO_WORKFLOW: dict[str, dict[str, Any]] = {
    "am.identity.login_new_device.v1": {
        "workflow_key": "identity.login_new_device",
        "category": "security",
        "critical": True,
    },
    "am.identity.password_changed.v1": {
        "workflow_key": "identity.password_changed",
        "category": "security",
        "critical": True,
    },
    "am.subscription.created.v1": {
        "workflow_key": "subscription.created",
        "category": "subscription",
        "critical": False,
    },
    "am.subscription.suspended.v1": {
        "workflow_key": "subscription.suspended",
        "category": "subscription",
        "critical": True,
    },
    "am.subscription.renewed.v1": {
        "workflow_key": "subscription.renewed",
        "category": "subscription",
        "critical": False,
    },
    "am.usage.quota_exceeded.v1": {
        "workflow_key": "usage.quota_exceeded",
        "category": "usage",
        "critical": False,
    },
}


def resolve_workflow(event_type: str) -> dict[str, Any] | None:
    return EVENT_TO_WORKFLOW.get(event_type)
