"""Bounce reports ("não entregue") read over IMAP and matched to outbox deliveries.

The SMTP relay accepts almost any address and reports a missing mailbox later, by mailing a
delivery status notification (RFC 3464) to the sender. The mail worker looks for those reports
in the sender's mailbox and marks the delivery as ``bounced``.

The mailbox may also hold personal mail, so only unread delivery reports are searched for on the
server, messages are read with BODY.PEEK (not marked as read), and only recognised reports are
flagged as read afterwards. Nothing from the messages is logged.
"""

import email
import imaplib
import logging
import re
import ssl
from dataclasses import dataclass
from datetime import timedelta
from email import policy
from uuid import UUID

from django.conf import settings
from django.utils import timezone

from .mailer import REFERENCE_HEADER
from .models import EmailDelivery

logger = logging.getLogger("exams.outbox")
LOOKBACK_DAYS = 7
MAX_MESSAGE_BYTES = 512 * 1024
MAX_PER_RUN = 50
PERMANENT_STATUS = re.compile(r"^5\.\d{1,3}\.\d{1,3}$")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class Bounce:
    recipient: str
    status: str
    reference: str = ""


def _recipient(block) -> str:
    """``Final-Recipient: rfc822; ana@example.com`` -> ``ana@example.com``."""
    field = block.get("Final-Recipient") or block.get("Original-Recipient") or ""
    return field.split(";", 1)[-1].strip().strip("<>").lower()


def _reference(part) -> str:
    """The X-PodeAbrir-Ref header of the original message, when the report quotes it."""
    if part.get_content_type() == "message/rfc822":
        original = part.get_payload(0)
    else:  # text/rfc822-headers
        original = email.message_from_string(part.get_content(), policy=policy.default)
    return (original.get(REFERENCE_HEADER) or "").strip()


def parse_bounces(raw: bytes) -> list[Bounce]:
    """Permanent failures (Action: failed, Status 5.x.x) in a delivery status notification."""
    report = email.message_from_bytes(raw, policy=policy.default)
    if report.get_content_type() != "multipart/report":
        return []
    if (report.get_param("report-type") or "").lower() != "delivery-status":
        return []
    failures, reference = [], ""
    for part in report.walk():
        kind = part.get_content_type()
        if kind == "message/delivery-status":
            for block in part.get_payload():
                status = (block.get("Status") or "").split(" ", 1)[0].strip()
                address = _recipient(block)
                if (block.get("Action") or "").strip().lower() == "failed" and PERMANENT_STATUS.match(status) and address:
                    failures.append((address, status))
        elif kind in ("message/rfc822", "text/rfc822-headers") and not reference:
            reference = _reference(part)
    return [Bounce(address, status, reference) for address, status in failures]


def _delivery_for(bounce: Bounce, now):
    """The sent delivery the report refers to: by reference when quoted, else the latest to that address."""
    sent = EmailDelivery.objects.filter(
        status="sent", sent_at__gte=now - timedelta(days=LOOKBACK_DAYS), to_address__iexact=bounce.recipient,
    )
    try:
        by_reference = sent.filter(pk=UUID(bounce.reference)).first() if bounce.reference else None
    except ValueError:
        by_reference = None
    return by_reference or sent.order_by("-sent_at").first()


def record_bounce(bounce: Bounce, now=None) -> EmailDelivery | None:
    delivery = _delivery_for(bounce, now or timezone.now())
    if delivery is None:
        return None
    delivery.status, delivery.last_error_code = "bounced", f"dsn:{bounce.status}"
    delivery.save(update_fields=["status", "last_error_code", "updated_at"])
    logger.info("delivery %s (%s) bounced: %s", delivery.id, delivery.purpose, bounce.status)
    return delivery


def bounce_checks_enabled() -> bool:
    return settings.EMAIL_ENABLED and bool(settings.EMAIL_IMAP_HOST)


def connect_imap():
    return imaplib.IMAP4_SSL(settings.EMAIL_IMAP_HOST, settings.EMAIL_IMAP_PORT,
                             ssl_context=ssl.create_default_context(), timeout=settings.EMAIL_SMTP_TIMEOUT_SECONDS)


def _imap_date(moment) -> str:
    """IMAP wants English month names whatever the server locale: 18-Nov-2026."""
    return f"{moment.day:02d}-{MONTHS[moment.month - 1]}-{moment.year}"


def _process_message(imap, uid: bytes, now) -> int:
    _, sized = imap.uid("FETCH", uid, "(RFC822.SIZE)")
    size = re.search(rb"RFC822\.SIZE (\d+)", sized[0] or b"")
    if not size or int(size.group(1)) > MAX_MESSAGE_BYTES:
        return 0
    _, fetched = imap.uid("FETCH", uid, "(BODY.PEEK[])")
    raw = next((item[1] for item in fetched if isinstance(item, tuple)), b"")
    bounces = parse_bounces(raw)
    if not bounces:
        return 0  # not a delivery report after all: left unread and untouched
    recorded = sum(record_bounce(bounce, now) is not None for bounce in bounces)
    imap.uid("STORE", uid, "+FLAGS", "(\\Seen)")
    return recorded


def check_bounces(connect=connect_imap, now=None) -> int:
    """Read new delivery reports and mark their deliveries as bounced. Returns how many were marked."""
    now = now or timezone.now()
    imap = connect()
    try:
        imap.login(settings.EMAIL_IMAP_USERNAME, settings.EMAIL_IMAP_PASSWORD)
        imap.select(settings.EMAIL_IMAP_FOLDER)
        since = _imap_date(now - timedelta(days=LOOKBACK_DAYS))
        _, found = imap.uid("SEARCH", None, "UNSEEN", "SINCE", since, "HEADER", "Content-Type", "delivery-status")
        uids = (found[0] or b"").split()[:MAX_PER_RUN]
        return sum(_process_message(imap, uid, now) for uid in uids)
    finally:
        try:
            imap.logout()
        except (imaplib.IMAP4.error, OSError) as error:
            logger.debug("imap logout failed after bounce check: %s", type(error).__name__)
