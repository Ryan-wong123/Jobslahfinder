import logging


SENSITIVE_LOG_KEYS = {
    "password",
    "password_hash",
    "token",
    "session_token",
    "reset_token",
    "api_key",
    "secret",
    "private_key",
}


def configure_logging(app_env: str) -> None:
    level = logging.INFO if app_env.lower() != "test" else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
