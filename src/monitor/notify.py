"""Email notification of scan alerts (digest)."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable

from .models import NEW, Alert

DESC_PREVIEW = 200
SMTPFactory = Callable[[str, int], smtplib.SMTP]


@dataclass(frozen=True, slots=True)
class EmailSettings:
    host: str | None
    port: int
    sender: str | None
    to: str | None
    user: str | None = None
    password: str | None = None
    use_tls: bool = True

    @classmethod
    def from_env(cls) -> "EmailSettings":
        user = os.environ.get("SMTP_USER")
        return cls(
            host=os.environ.get("SMTP_HOST"),
            port=int(os.environ.get("SMTP_PORT", "587")),
            sender=os.environ.get("SMTP_FROM") or user,
            to=os.environ.get("SMTP_TO") or os.environ.get("NOTIFY_EMAIL"),
            user=user,
            password=os.environ.get("SMTP_PASSWORD"),
            use_tls=os.environ.get("SMTP_TLS", "true").lower() != "false",
        )

    def is_complete(self) -> bool:
        return bool(self.host and self.sender and self.to)


def _alert_block(alert: Alert) -> str:
    v = alert.candidate
    label = "【新视频】" if alert.reason == NEW else "【爆款】"
    desc = v.description.strip().replace("\r", "")
    if len(desc) > DESC_PREVIEW:
        desc = desc[:DESC_PREVIEW] + "…"
    lines = [
        f"{label} {v.title}",
        f"频道: {v.channel}    分类: {v.category}",
        f"播放: {v.view_count if v.view_count is not None else '—'}    "
        f"点赞: {v.like_count if v.like_count is not None else '—'}",
        f"链接: {v.url}",
    ]
    if v.tags:
        lines.append(f"标签: {', '.join(v.tags)}")
    if desc:
        lines.append(f"简介: {desc}")
    return "\n".join(lines)


def build_digest(alerts: list[Alert]) -> tuple[str, str]:
    new = sum(1 for a in alerts if a.reason == NEW)
    trending = len(alerts) - new
    subject = f"[Transdub] {len(alerts)} 条线索（新视频 {new} / 爆款 {trending}）"
    body = "\n\n".join(_alert_block(a) for a in alerts)
    return subject, body


def send_email(
    subject: str,
    body: str,
    settings: EmailSettings,
    smtp_factory: SMTPFactory = smtplib.SMTP,
) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.sender
    message["To"] = settings.to
    message.set_content(body)

    server = smtp_factory(settings.host, settings.port)
    try:
        if settings.use_tls:
            server.starttls()
        if settings.user:
            server.login(settings.user, settings.password)
        server.send_message(message)
    finally:
        server.quit()


def notify(
    alerts: list[Alert],
    settings: EmailSettings,
    smtp_factory: SMTPFactory = smtplib.SMTP,
) -> bool:
    """Send a digest email for the alerts. Returns False if nothing was sent."""
    if not alerts:
        return False
    subject, body = build_digest(alerts)
    send_email(subject, body, settings, smtp_factory)
    return True
