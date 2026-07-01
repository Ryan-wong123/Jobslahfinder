from __future__ import annotations

from email.message import EmailMessage
import smtplib
from urllib.parse import quote

from app.core.config import Settings


def build_password_reset_url(settings: Settings, token: str) -> str:
    base_url = settings.frontend_base_url.rstrip("/")
    return f"{base_url}/reset-password?token={quote(token, safe='')}"


def send_password_reset_email(settings: Settings, *, to_email: str, token: str) -> None:
    reset_url = build_password_reset_url(settings, token)

    if not settings.smtp_host or not settings.smtp_from_email:
        raise RuntimeError("password_reset_email_not_configured")

    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = "Reset your Secure Job Platform password"
    message.set_content(
        "\n".join(
            [
                "We received a request to reset your password.",
                "",
                f"Open this link to set a new password: {reset_url}",
                "",
                f"This link expires in {settings.password_reset_expire_minutes} minutes.",
                "If you did not request this, you can ignore this email.",
            ]
        )
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)
