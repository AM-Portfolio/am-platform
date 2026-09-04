"""Helper unit tests."""

from am_user_platform.modules.ai.services.helpers import title_from_first_message


def test_title_from_short_message() -> None:
    assert title_from_first_message("Show my portfolio") == "Show my portfolio"


def test_title_truncates_long_message() -> None:
    long_text = "a" * 60
    title = title_from_first_message(long_text)
    assert len(title) <= 50
    assert title.endswith("…")


def test_title_default_for_blank() -> None:
    assert title_from_first_message("   ") == "New chat"
