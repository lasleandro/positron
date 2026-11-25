"""Grant lifecycle rules and the hash-chained access history."""

import re
from datetime import timedelta
from hashlib import sha256

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Grant, GrantEvent, OwnerProfile

# Lifetime presets offered by the UI, in minutes; the server accepts only these.
IN_PERSON_MINUTES = (15, 45, 120, 480)
LINK_MINUTES = (60, 24 * 60, 7 * 24 * 60)
EXTEND_MINUTES = (15, 60, 24 * 60)
MAX_OPENS_LIMIT = 20
GENESIS = "0" * 64


def grant_state(grant, now=None) -> str:
    """idle | pending | active | expired | revoked | exhausted | locked."""
    if grant is None:
        return "idle"
    if grant.ended_at:
        return grant.end_reason or "revoked"
    now = now or timezone.now()
    if grant.expires_at:
        if grant.expires_at <= now:
            return "expired"
        if grant.max_opens is not None and grant.opens >= grant.max_opens:
            return "exhausted"
        return "active"
    return "pending" if grant.pair_until and grant.pair_until > now else "expired"


def capped_expiry(start, minutes: int):
    return min(start + timedelta(minutes=minutes), timezone.now() + timedelta(minutes=settings.GRANT_MAX_MINUTES))


def end_grant(grant, reason: str) -> None:
    """Stop a grant for good: no more content, and its re-sealed keys are deleted."""
    grant.ended_at = timezone.now()
    grant.end_reason = reason
    grant.save(update_fields=["ended_at", "end_reason"])
    grant.grantdocument_set.all().delete()


def browser_agent(request) -> str:
    """Coarse browser family for the history ("Chrome · Windows"). No IP is stored."""
    ua = request.META.get("HTTP_USER_AGENT", "")
    browser = next((name for pattern, name in (
        (r"Edg/", "Edge"), (r"OPR/", "Opera"), (r"Firefox/", "Firefox"),
        (r"Chrome/", "Chrome"), (r"Safari/", "Safari"),
    ) if re.search(pattern, ua)), "Navegador")
    system = next((name for pattern, name in (
        (r"Android", "Android"), (r"iPhone|iPad", "iOS"), (r"Windows", "Windows"),
        (r"Mac OS X", "macOS"), (r"Linux", "Linux"),
    ) if re.search(pattern, ua)), "")
    return f"{browser} · {system}" if system else browser


def event_material(prev_hash: str, event: GrantEvent) -> str:
    """Canonical text hashed into the chain; the browser rebuilds the same string to verify it."""
    grant_id = str(event.grant_id) if event.grant_id else ""
    return "|".join([
        prev_hash, event.at.isoformat(), event.channel, event.kind, grant_id,
        event.document, event.agent, event.detail,
    ])


def record_event(grant, kind: str, *, document: str = "", agent: str = "", detail: str = "") -> GrantEvent:
    """Append to the owner's chain. The owner's profile row serializes concurrent appends."""
    with transaction.atomic():
        OwnerProfile.objects.get_or_create(user_id=grant.owner_id)
        OwnerProfile.objects.select_for_update().get(user_id=grant.owner_id)
        last = GrantEvent.objects.filter(owner_id=grant.owner_id).order_by("-id").first()
        event = GrantEvent(
            owner_id=grant.owner_id, grant=grant, channel=grant.channel, kind=kind,
            document=document, agent=agent[:40], detail=detail[:120], at=timezone.now(),
            prev_hash=last.hash if last else GENESIS,
        )
        event.hash = sha256(event_material(event.prev_hash, event).encode()).hexdigest()
        event.save()
        return event


def is_active_reader_grant(grant: Grant) -> bool:
    return grant is not None and grant.channel != Grant.LINK and grant_state(grant) == "active"
