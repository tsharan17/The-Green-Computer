"""Outgoing email behind an interface. No vendor is required.

- ``ConsoleEmailSender`` (default): writes the message to the server log and keeps the last messages
  in memory, so a self-hosted install without mail works and a developer can read reset links.
- ``SmtpEmailSender``: used when GC_SMTP_HOST is set (any SMTP relay).
- ``BrevoEmailSender``: used when GC_BREVO_API_KEY is set. Sends over HTTPS, for hosts that block
  outgoing SMTP (Render's free plan does).

Every sender is wrapped so a failed delivery is logged and never fails the request that sent it: the
account or reset link is already saved, and the person can ask for the email again.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Protocol

import httpx

log = logging.getLogger("green_computer.email")


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str
    sent_at: datetime


class EmailSender(Protocol):
    name: str

    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    name = "console"

    def __init__(self, keep: int = 50) -> None:
        self.outbox: deque[OutgoingEmail] = deque(maxlen=keep)
        self._lock = threading.Lock()

    def send(self, to: str, subject: str, body: str) -> None:
        with self._lock:
            self.outbox.append(OutgoingEmail(to, subject, body, datetime.now(UTC)))
        log.warning("EMAIL (console sender, not delivered) to=%s subject=%s\n%s", to, subject, body)


class SmtpEmailSender:
    name = "smtp"

    def __init__(self, host: str, port: int, user: str | None, password: str | None,
                 sender: str, starttls: bool) -> None:  # fmt: skip
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.starttls = sender, starttls

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=15) as s:
            if self.starttls:
                s.starttls(context=ssl.create_default_context())
            if self.user:
                s.login(self.user, self.password or "")
            s.send_message(msg)


class BrevoEmailSender:
    """Brevo's transactional email API. The sender address must be verified in Brevo."""

    name = "brevo"
    URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, api_key: str, sender: str, transport: httpx.BaseTransport | None = None) -> None:
        self.api_key = api_key
        self.sender_name, self.sender_email = parseaddr(sender)
        self.http = httpx.Client(timeout=15.0, transport=transport)

    def send(self, to: str, subject: str, body: str) -> None:
        r = self.http.post(self.URL, headers={"api-key": self.api_key, "accept": "application/json"}, json={
            "sender": {"name": self.sender_name or "The Green Computer", "email": self.sender_email},
            "to": [{"email": to}], "subject": subject, "textContent": body,
        })  # fmt: skip
        if r.status_code >= 300:
            raise RuntimeError(f"Brevo refused the message: HTTP {r.status_code}")


class GuardedEmailSender:
    """Logs a failed delivery instead of raising (see the module note)."""

    def __init__(self, inner: EmailSender) -> None:
        self.inner = inner
        self.name = inner.name

    def send(self, to: str, subject: str, body: str) -> None:
        try:
            self.inner.send(to, subject, body)
        except Exception as e:  # noqa: BLE001 - any delivery failure is reported the same way
            log.error("email not delivered via %s to a %s address: %s: %s", self.name,
                      to.rpartition("@")[2] or "?", type(e).__name__, e)  # fmt: skip


def make_email_sender() -> EmailSender:
    env = os.environ.get
    sender_addr = env("GC_EMAIL_FROM") or env("GC_SMTP_FROM") or "The Green Computer <no-reply@localhost>"
    if env("GC_BREVO_API_KEY"):
        return GuardedEmailSender(BrevoEmailSender(env("GC_BREVO_API_KEY") or "", sender_addr))
    host = env("GC_SMTP_HOST")
    if host:
        return GuardedEmailSender(SmtpEmailSender(
            host, int(env("GC_SMTP_PORT") or 587), env("GC_SMTP_USER"), env("GC_SMTP_PASSWORD"), sender_addr,
            (env("GC_SMTP_STARTTLS") or "1") not in ("0", "false", "no"),
        ))  # fmt: skip
    return ConsoleEmailSender()
