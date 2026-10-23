"""Background job handlers."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app.config import settings


def _email_fields(payload: dict) -> tuple[str, str, str]:
    recipient = payload.get("to")
    if not isinstance(recipient, str) or not recipient.strip():
        raise ValueError("Email payload requires a non-empty 'to' address")
    if not settings.EMAIL_FROM:
        raise RuntimeError("EMAIL_FROM is not configured")
    subject = str(payload.get("subject", "Background job notification"))
    body = str(payload.get("body", ""))
    return recipient, subject, body


async def _send_email_resend(payload: dict) -> None:
    """Send an email through Resend's HTTPS API."""
    recipient, subject, body = _email_fields(payload)
    if not settings.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.EMAIL_FROM,
                "to": [recipient],
                "subject": subject,
                "text": body,
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Resend rejected email with HTTP {exc.response.status_code}"
            ) from exc


def _send_email_sync(payload: dict) -> None:
    """Send one email through an SMTP-compatible provider."""
    recipient, subject, body = _email_fields(payload)
    if not settings.SMTP_HOST:
        raise RuntimeError("SMTP_HOST is not configured")
    if settings.SMTP_USE_TLS and settings.SMTP_USE_SSL:
        raise RuntimeError("SMTP_USE_TLS and SMTP_USE_SSL cannot both be enabled")

    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    smtp_factory = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    with smtp_factory(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as client:
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
    """Send an email through Resend, or SMTP when Resend is not configured."""
    if payload.get("force_fail"):
        raise ValueError("Simulated email failure")
    if settings.RESEND_API_KEY:
        await _send_email_resend(payload)
    else:
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
