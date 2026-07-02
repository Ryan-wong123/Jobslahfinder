from __future__ import annotations

import html
import re
import unicodedata
from typing import Any, Literal


HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
MULTILINE_WHITESPACE = {"\n", "\r", "\t"}

HtmlPolicy = Literal["allow", "reject", "strip"]
OverflowPolicy = Literal["error", "truncate"]
ControlPolicy = Literal["reject", "strip"]


def normalize_text_value(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value))


def is_unsafe_control_character(character: str, *, allow_multiline: bool) -> bool:
    if allow_multiline and character in MULTILINE_WHITESPACE:
        return False
    category = unicodedata.category(character)
    return category in {"Cc", "Cf", "Cs", "Co", "Cn"}


def has_unsafe_control_characters(text: str, *, allow_multiline: bool) -> bool:
    return any(is_unsafe_control_character(character, allow_multiline=allow_multiline) for character in text)


def strip_unsafe_control_characters(text: str, *, allow_multiline: bool) -> str:
    return "".join(
        " " if is_unsafe_control_character(character, allow_multiline=allow_multiline) else character
        for character in text
    )


def sanitize_text(
    value: Any,
    *,
    field_name: str,
    max_length: int,
    empty_to_none: bool = False,
    html_policy: HtmlPolicy = "reject",
    overflow: OverflowPolicy = "error",
    control_policy: ControlPolicy = "reject",
    collapse_whitespace: bool = False,
    allow_multiline: bool = True,
    reject_placeholders: bool = False,
) -> str | None:
    text = normalize_text_value(value)
    text = html.unescape(text)

    if html_policy == "reject" and HTML_TAG_PATTERN.search(text):
        raise ValueError(f"Invalid {field_name}.")
    if html_policy == "strip":
        text = HTML_TAG_PATTERN.sub(" ", text)

    if has_unsafe_control_characters(text, allow_multiline=allow_multiline) and control_policy == "reject":
        raise ValueError(f"Invalid {field_name}.")
    if control_policy == "strip":
        text = strip_unsafe_control_characters(text, allow_multiline=allow_multiline)
    if not allow_multiline and any(character in text for character in ("\n", "\r", "\t")):
        raise ValueError(f"Invalid {field_name}.")

    text = WHITESPACE_PATTERN.sub(" ", text) if collapse_whitespace else text.strip()
    text = text.strip()

    if reject_placeholders and text in {"-", "N/A", "n/a", "NA", "na"}:
        text = ""
    if not text and empty_to_none:
        return None
    if len(text) > max_length:
        if overflow == "truncate":
            text = text[:max_length].strip()
        else:
            raise ValueError(f"Invalid {field_name}.")
    if not text and empty_to_none:
        return None
    return text


def sanitize_required_text(
    value: Any,
    *,
    field_name: str,
    max_length: int,
    html_policy: HtmlPolicy = "reject",
    overflow: OverflowPolicy = "error",
    control_policy: ControlPolicy = "reject",
    collapse_whitespace: bool = False,
    allow_multiline: bool = True,
) -> str:
    cleaned = sanitize_text(
        value,
        field_name=field_name,
        max_length=max_length,
        empty_to_none=True,
        html_policy=html_policy,
        overflow=overflow,
        control_policy=control_policy,
        collapse_whitespace=collapse_whitespace,
        allow_multiline=allow_multiline,
    )
    if cleaned is None:
        raise ValueError(f"Invalid {field_name}.")
    return cleaned
