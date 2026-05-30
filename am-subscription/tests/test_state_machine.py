from am_platform_common import ConflictError

from am_subscription.core.state_machine import validate_transition
import pytest


def test_valid_transitions():
    validate_transition("trial", "active")
    validate_transition("active", "paused")
    validate_transition("past_due", "suspended")


def test_invalid_transition_raises():
    with pytest.raises(ConflictError):
        validate_transition("cancelled", "active")
