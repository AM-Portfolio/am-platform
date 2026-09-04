from am_platform_common import BadRequestError, ConflictError

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "trial": {"active", "expired"},
    "active": {"past_due", "paused", "cancelled"},
    "past_due": {"active", "suspended"},
    "paused": {"active"},
    "suspended": {"active", "cancelled"},
    "cancelled": set(),
    "expired": set(),
}

ACTIVE_STATES = {"trial", "active", "past_due", "paused"}
METERING_STATES = {"trial", "active", "past_due"}


def validate_transition(current: str, target: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ConflictError(
            message=f"Cannot transition subscription from '{current}' to '{target}'",
            details={
                "current_state": current,
                "target_state": target,
                "allowed": sorted(allowed),
            },
        )


def assert_active_for_usage(state: str) -> None:
    if state not in METERING_STATES:
        raise BadRequestError(
            message=f"Subscription state '{state}' does not allow usage",
            details={"state": state},
        )
