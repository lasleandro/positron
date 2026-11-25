"""Durable email outbox with bounded retry (ported from agenda_ai services/auth_emails.py)."""

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .email_templates import invitation_email, password_changed_email, password_reset_email, read_request_email
from .mailer import EmailPermanentError, EmailRetryableError, default_sender
from .models import EmailDelivery, Invitation, PasswordResetToken

logger = logging.getLogger("exams.outbox")
PENDING = ("queued", "processing", "retry_wait")
BATCH_SIZE = 20


def token_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def enqueue(purpose: str, to_address: str, user=None, grants_staff: bool = False) -> EmailDelivery:
    """Queue one delivery; an identical one still pending is reused (double clicks reconcile)."""
    existing = EmailDelivery.objects.filter(
        purpose=purpose, to_address=to_address, status__in=PENDING,
    ).first()
    if existing:
        return existing
    return EmailDelivery.objects.create(purpose=purpose, to_address=to_address, user=user, grants_staff=grants_staff)


def issue_invitation(email: str, grants_staff: bool) -> str:
    """Supersede unused invitations for this address and return a fresh raw token."""
    now = timezone.now()
    Invitation.objects.filter(email=email, used_at__isnull=True).update(used_at=now)
    raw = secrets.token_urlsafe(32)
    Invitation.objects.create(
        digest=token_digest(raw), email=email, grants_staff=grants_staff,
        expires_at=now + timedelta(hours=settings.INVITATION_HOURS),
    )
    return raw


def issue_reset_token(user) -> str:
    now = timezone.now()
    PasswordResetToken.objects.filter(user=user, consumed_at__isnull=True).update(consumed_at=now)
    raw = secrets.token_urlsafe(32)
    PasswordResetToken.objects.create(
        digest=token_digest(raw), user=user, expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_MINUTES),
    )
    return raw


def render(delivery: EmailDelivery):
    """Issue the single-use token (if any) at render time; links carry it in the URL fragment."""
    if delivery.purpose == EmailDelivery.INVITATION:
        raw = issue_invitation(delivery.to_address, delivery.grants_staff)
        return invitation_email(delivery.to_address, f"{settings.ORIGIN}/cadastro/#{raw}", settings.INVITATION_HOURS)
    if delivery.purpose == EmailDelivery.PASSWORD_RESET:
        if delivery.user is None or not delivery.user.is_active:
            raise EmailPermanentError("user_unavailable")
        raw = issue_reset_token(delivery.user)
        return password_reset_email(
            delivery.to_address, f"{settings.ORIGIN}/redefinir-senha/#{raw}", settings.PASSWORD_RESET_MINUTES,
        )
    if delivery.purpose == EmailDelivery.PASSWORD_CHANGED:
        return password_changed_email(delivery.to_address)
    if delivery.purpose == EmailDelivery.READ_REQUEST:
        return read_request_email(delivery.to_address, f"{settings.ORIGIN}/compartilhamentos/")
    raise EmailPermanentError("unsupported_purpose")


def recover_stale(now) -> None:
    """A worker that died mid-send leaves rows in 'processing'; give them another attempt."""
    stale_before = now - timedelta(seconds=settings.EMAIL_PROCESSING_TIMEOUT_SECONDS)
    EmailDelivery.objects.filter(status="processing", updated_at__lte=stale_before).update(
        status="retry_wait", next_attempt_at=now, last_error_code="worker_recovery",
    )


def claim_due(now) -> list:
    with transaction.atomic():
        due = list(
            EmailDelivery.objects.select_for_update(skip_locked=True)
            .filter(status__in=("queued", "retry_wait"))
            .exclude(next_attempt_at__gt=now)
            .order_by("created_at")[:BATCH_SIZE]
        )
        for delivery in due:
            delivery.status = "processing"
            delivery.attempt_count += 1
            delivery.next_attempt_at = None
            delivery.save(update_fields=["status", "attempt_count", "next_attempt_at", "updated_at"])
    return due


def schedule_retry(delivery: EmailDelivery, code: str, now) -> None:
    delivery.last_error_code = code
    if delivery.attempt_count >= settings.EMAIL_MAX_ATTEMPTS:
        delivery.status = "failed"
        return
    delivery.status = "retry_wait"
    delay = settings.EMAIL_RETRY_BASE_SECONDS * (2 ** (delivery.attempt_count - 1))
    delivery.next_attempt_at = now + timedelta(seconds=delay)


def deliver(delivery: EmailDelivery, sender, now) -> None:
    try:
        with transaction.atomic():
            message = render(delivery)
            sender.send(message)
    except EmailPermanentError as exc:
        logger.error("delivery %s (%s) failed permanently: %s", delivery.id, delivery.purpose, exc)
        delivery.status, delivery.last_error_code = "failed", "permanent"
    except EmailRetryableError as exc:
        logger.warning("delivery %s (%s) retryable failure #%s: %s", delivery.id, delivery.purpose,
                       delivery.attempt_count, exc)
        schedule_retry(delivery, "retryable", now)
    except Exception:
        logger.exception("delivery %s (%s) unexpected error", delivery.id, delivery.purpose)
        schedule_retry(delivery, "unexpected", now)
    else:
        logger.info("delivery %s (%s) sent", delivery.id, delivery.purpose)
        delivery.status, delivery.sent_at, delivery.last_error_code = "sent", now, ""
    delivery.save(update_fields=["status", "sent_at", "last_error_code", "next_attempt_at", "updated_at"])


def process_due(sender=None, now=None) -> int:
    """Claim and send due deliveries. Returns how many were attempted."""
    now = now or timezone.now()
    recover_stale(now)
    due = claim_due(now)
    if not due:
        return 0
    active_sender = sender or default_sender()
    for delivery in due:
        deliver(delivery, active_sender, now)
    return len(due)
