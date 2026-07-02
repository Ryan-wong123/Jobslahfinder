import logging
import re
from collections.abc import Mapping


SENSITIVE_LOG_KEYS = {
    "authorization",
    "gemini_api_key",
    "password",
    "password_hash",
    "api_key",
    "private_key",
    "prompt",
    "reset_token",
    "resume_content",
    "resume_text",
    "secret",
    "session_token",
    "token",
}

SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)\b("
    r"api[_-]?key|authorization|password|password[_-]?hash|private[_-]?key|"
    r"prompt|reset[_-]?token|secret|session[_-]?token|token"
    r")\b\s*([=:])\s*([^\s,;]+)"
)


def is_sensitive_log_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in SENSITIVE_LOG_KEYS or any(
        marker in normalized
        for marker in ("api_key", "apikey", "password", "private_key", "prompt", "secret", "token")
    )


def redact_log_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if is_sensitive_log_key(str(key)) else redact_log_value(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_log_value(item) for item in value)
    if isinstance(value, list):
        return [redact_log_value(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_VALUE_PATTERN.sub(r"\1\2[REDACTED]", value)
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_log_value(record.msg)
        if record.args:
            record.args = redact_log_value(record.args)
        return True


def configure_logging(app_env: str) -> None:
    level = logging.INFO if app_env.lower() != "test" else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    redacting_filter = RedactingFilter()
    root_logger = logging.getLogger()
    root_logger.addFilter(redacting_filter)
    for handler in root_logger.handlers:
        handler.addFilter(redacting_filter)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
