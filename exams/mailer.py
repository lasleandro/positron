"""Provider-neutral SMTP sender (ported from agenda_ai app/integrations/email)."""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger("exams.outbox")
# Outbox delivery id; bounce reports quote the original headers, so a bounce finds its delivery.
REFERENCE_HEADER = "X-PodeAbrir-Ref"


class EmailPermanentError(Exception):
    """Will not succeed without configuration or recipient changes."""


class EmailRetryableError(Exception):
    """Transient transport failure, suitable for bounded retry."""


@dataclass(frozen=True)
class InlineImage:
    """PNG embedded in the message and referenced from the HTML as ``cid:<content_id>``."""

    content_id: str
    filename: str
    data: bytes


@dataclass(frozen=True)
class OutboundEmail:
    to_address: str
    subject: str
    html_body: str
    text_body: str
    reply_to: str = ""
    images: tuple[InlineImage, ...] = ()
    reference: str = ""


class SmtpEmailSender:
    """Implicit TLS (ssl) or STARTTLS with verified certificates."""

    def __init__(self) -> None:
        missing = [name for name in (
            "EMAIL_SMTP_HOST", "EMAIL_SMTP_USERNAME", "EMAIL_SMTP_PASSWORD", "EMAIL_FROM_ADDRESS",
        ) if not getattr(settings, name)]
        if missing:
            raise ImproperlyConfigured(f"Missing SMTP settings: {', '.join(missing)}")
        if settings.EMAIL_SMTP_SECURITY not in {"ssl", "starttls"}:
            raise ImproperlyConfigured("EMAIL_SMTP_SECURITY must be ssl or starttls")

    def _mime(self, message: OutboundEmail) -> str:
        body = MIMEMultipart("alternative")
        body.attach(MIMEText(message.text_body, "plain", "utf-8"))
        body.attach(MIMEText(message.html_body, "html", "utf-8"))
        mime = body
        if message.images:
            mime = MIMEMultipart("related")
            mime.attach(body)
            for image in message.images:
                part = MIMEImage(image.data, "png")
                part.add_header("Content-ID", f"<{image.content_id}>")
                part.add_header("Content-Disposition", "inline", filename=image.filename)
                mime.attach(part)
        mime["Subject"] = message.subject
        mime["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>"
        mime["To"] = message.to_address
        reply_to = message.reply_to or settings.EMAIL_REPLY_TO
        if reply_to:
            mime["Reply-To"] = reply_to
        if message.reference:
            mime[REFERENCE_HEADER] = message.reference
        return mime.as_string()

    def send(self, message: OutboundEmail) -> None:
        context = ssl.create_default_context()
        host, port, timeout = settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT, settings.EMAIL_SMTP_TIMEOUT_SECONDS
        try:
            if settings.EMAIL_SMTP_SECURITY == "ssl":
                server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
            else:
                server = smtplib.SMTP(host, port, timeout=timeout)
            with server:
                if settings.EMAIL_SMTP_SECURITY == "starttls":
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                server.login(settings.EMAIL_SMTP_USERNAME, settings.EMAIL_SMTP_PASSWORD)
                server.sendmail(settings.EMAIL_FROM_ADDRESS, [message.to_address], self._mime(message))
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as exc:
            raise EmailPermanentError(type(exc).__name__) from exc
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            raise EmailRetryableError(type(exc).__name__) from exc


class ConsoleEmailSender:
    """Development only: print the text body (including links) instead of sending."""

    def send(self, message: OutboundEmail) -> None:
        logger.info("EMAIL (console) to=%s subject=%s\n%s", message.to_address, message.subject, message.text_body)


def default_sender():
    return SmtpEmailSender() if settings.EMAIL_ENABLED else ConsoleEmailSender()
