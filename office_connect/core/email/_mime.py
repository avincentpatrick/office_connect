"""Shared MIME assembly for the email drivers (stdlib ``email`` only).

Both SMTP and Gmail need the same RFC-5322 message; building it once keeps the
two transports byte-identical.
"""

from __future__ import annotations

from email.message import EmailMessage as MimeMessage

from office_connect.core.email.base import EmailMessage


def build_mime(message: EmailMessage, sender: str) -> MimeMessage:
    mime = MimeMessage()
    mime["From"] = sender
    mime["To"] = ", ".join(message.to)
    if message.cc:
        mime["Cc"] = ", ".join(message.cc)
    mime["Subject"] = message.subject
    mime.set_content(message.text_body)
    if message.html_body:
        mime.add_alternative(message.html_body, subtype="html")
    return mime
