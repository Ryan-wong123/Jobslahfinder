import pytest

from app.security.text import sanitize_required_text, sanitize_text
from app.services.jobs import clean_text


def test_sanitize_text_rejects_html_and_hidden_controls_by_default() -> None:
    assert (
        sanitize_text(
            "  Cafe\u0301 analyst  ",
            field_name="summary",
            max_length=40,
            empty_to_none=True,
        )
        == "Caf\u00e9 analyst"
    )

    with pytest.raises(ValueError, match="Invalid summary"):
        sanitize_text("<script>alert(1)</script>", field_name="summary", max_length=40)

    with pytest.raises(ValueError, match="Invalid summary"):
        sanitize_text("safe\u202etext", field_name="summary", max_length=40)


def test_sanitize_text_can_strip_html_controls_and_collapse_whitespace() -> None:
    assert (
        sanitize_required_text(
            "<b>Hello</b>\u0001   world",
            field_name="generated_text",
            max_length=40,
            html_policy="strip",
            control_policy="strip",
            collapse_whitespace=True,
        )
        == "Hello world"
    )


def test_sanitize_text_enforces_length_or_truncates_explicitly() -> None:
    with pytest.raises(ValueError, match="Invalid summary"):
        sanitize_text("x" * 41, field_name="summary", max_length=40)

    assert (
        sanitize_text(
            "x" * 41,
            field_name="summary",
            max_length=40,
            overflow="truncate",
        )
        == "x" * 40
    )


def test_job_clean_text_strips_untrusted_html_and_control_characters() -> None:
    cleaned = clean_text(
        "<script>alert(1)</script><p>Protect\u202e platforms.</p>\u0000",
        max_length=200,
    )

    assert "<script>" not in cleaned
    assert "<p>" not in cleaned
    assert "\u202e" not in cleaned
    assert "\u0000" not in cleaned
    assert "Protect platforms." in cleaned
