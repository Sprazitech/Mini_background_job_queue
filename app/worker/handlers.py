"""Background job handlers."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings


def _send_email_sync(payload: dict) -> None:
    """Send one email through an SMTP-compatible provider."""
    recipient = payload.get("to")
    if not isinstance(recipient, str) or not recipient.strip():
        raise ValueError("Email payload requires a non-empty 'to' address")
    if not settings.EMAIL_FROM:
        raise RuntimeError("EMAIL_FROM is not configured")
    if not settings.SMTP_HOST:
        raise RuntimeError("SMTP_HOST is not configured")
    if settings.SMTP_USE_TLS and settings.SMTP_USE_SSL:
        raise RuntimeError("SMTP_USE_TLS and SMTP_USE_SSL cannot both be enabled")

    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = recipient
    message["Subject"] = str(payload.get("subject", "Background job notification"))
    message.set_content(str(payload.get("body", "")))

    smtp_factory = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    with smtp_factory(
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        timeout=30,
    ) as client:
        client.ehlo()
        if settings.SMTP_USE_TLS:
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        if settings.SMTP_USERNAME:
            if not settings.SMTP_PASSWORD:
                raise RuntimeError("SMTP_PASSWORD is required with SMTP_USERNAME")
            client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        client.send_message(message)


async def handle_send_email(payload: dict) -> None:
    """Send an email asynchronously through the configured SMTP provider."""
    if payload.get("force_fail"):
        raise ValueError("Simulated email failure")
    await asyncio.to_thread(_send_email_sync, payload)


async def handle_generate_report(payload: dict) -> None:
    """Generate a report placeholder until a report provider is integrated."""
    await asyncio.sleep(3)
    if payload.get("force_error"):
        raise RuntimeError("Simulated report error")


HANDLERS = {
    "send_email": handle_send_email,
    "generate_report": handle_generate_report,
}
