"""Owner side of every short-lived permission ("Compartilhamentos").

The browser re-seals the chosen data keys for each grant (ECDH for readers, a random link key
for links); the server only stores those sealed copies and enforces the policy.
"""

from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .crypto_format import comparison_code, fingerprint, public_key_bytes, wrapped_key_bytes
from .library import SUMMARY_FIELDS, document_summary
from .models import Document, Grant, GrantDocument
from .policy import (
    EXTEND_MINUTES, IN_PERSON_MINUTES, LINK_MINUTES, MAX_OPENS_LIMIT, capped_expiry, end_grant, grant_state,
    record_event,
)
from .reader import CODE_PATTERN
from .responses import ErrorCode, fail, ok
from .security import allow_attempt, audit, json_body, owner_required, rate_key

RECENT_DAYS = 7
LIST_LIMIT = 50


class ShareError(ValueError):
    def __init__(self, code: ErrorCode):
        super().__init__(code.value)
        self.code = code


def chosen_documents(body: dict, owner) -> set[str]:
    selected = body.get("documents")
    chosen = {str(item) for item in selected} if isinstance(selected, list) else set()
    owned = {str(pk) for pk in Document.objects.filter(owner=owner).values_list("id", flat=True)}
    if not chosen or not chosen.issubset(owned):
        raise ShareError(ErrorCode.NO_EXAMS_SELECTED)
    return chosen


def sealed_keys(body: dict, chosen: set[str]) -> dict:
    """Exactly one browser-sealed data key per chosen document."""
    keys = body.get("share_keys")
    if not isinstance(keys, dict) or keys.keys() != chosen:
        raise ShareError(ErrorCode.INVALID_SHARE_KEYS)
    for value in keys.values():
        try:
            wrapped_key_bytes(value if isinstance(value, str) else "")
        except ValueError as error:
            raise ShareError(ErrorCode.INVALID_SHARE_KEYS) from error
    return keys


def sender_key(body: dict) -> str:
    value = body.get("sender_key", "")
    try:
        public_key_bytes(value if isinstance(value, str) else "")
    except ValueError as error:
        raise ShareError(ErrorCode.INVALID_SHARE_KEYS) from error
    return value


def lifetime(body: dict, allowed: tuple[int, ...], default: int | None = None) -> int:
    minutes = body.get("minutes", default)
    if minutes not in allowed:
        raise ShareError(ErrorCode.INVALID_POLICY)
    return minutes


def attach(grant: Grant, keys: dict) -> None:
    GrantDocument.objects.bulk_create([
        GrantDocument(grant=grant, document_id=document_id, wrapped_key=key) for document_id, key in keys.items()
    ])


def grant_payload(grant: Grant, duplicates: Counter | None = None) -> dict:
    state = grant_state(grant)
    payload = {
        "id": str(grant.id), "channel": grant.channel, "state": state, "label": grant.label,
        "created_at": grant.created_at.isoformat(),
        "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
        "ended_at": grant.ended_at.isoformat() if grant.ended_at else None,
        "viewing_until": grant.viewing_until.isoformat() if grant.viewing_until else None,
        "max_opens": grant.max_opens, "opens": grant.opens, "pin": bool(grant.pin_verifier),
        "code": grant.pairing_code or "",
        "documents": [document_summary(document) for document in grant.documents.all()],
    }
    if state == "pending" and grant.channel == Grant.HANDLE:
        code = comparison_code(grant.recipient_key, grant.nonce)
        payload.update(
            recipient_key=grant.recipient_key, nonce=grant.nonce, pair_until=grant.pair_until.isoformat(),
            duplicate=bool(duplicates and duplicates[code] > 1),
        )
    return payload


@require_GET
@owner_required
def list_grants(request):
    now = timezone.now()
    recent = now - timedelta(days=RECENT_DAYS)
    grants = list(
        Grant.objects.filter(owner=request.user)
        .filter(Q(ended_at__isnull=True, expires_at__gt=now) | Q(pair_until__gt=now, expires_at__isnull=True)
                | Q(created_at__gte=recent))
        .order_by("-created_at")
        .prefetch_related(Prefetch("documents", queryset=Document.objects.only(*SUMMARY_FIELDS)))[:LIST_LIMIT]
    )
    pending = [g for g in grants if g.channel == Grant.HANDLE and grant_state(g, now) == "pending"]
    duplicates = Counter(comparison_code(g.recipient_key, g.nonce) for g in pending)
    return ok([grant_payload(grant, duplicates) for grant in grants])


@require_GET
@owner_required
def pending_requests(request):
    """Cheap poll for the app shell: @handle requests waiting for this owner."""
    now = timezone.now()
    pending = Grant.objects.filter(
        owner=request.user, channel=Grant.HANDLE, expires_at__isnull=True, ended_at__isnull=True, pair_until__gt=now,
    ).order_by("-created_at").values("id", "pair_until")
    items = [{"id": str(item["id"]), "pair_until": item["pair_until"].isoformat()} for item in pending[:10]]
    return ok({"count": len(items), "items": items})


@require_GET
@owner_required
def pairing_key(request, code):
    if not CODE_PATTERN.fullmatch(code):
        return fail(ErrorCode.PAIRING_UNAVAILABLE, 404)
    if not allow_attempt(rate_key("lookup", str(request.user.pk)), 30, 300):
        return fail(ErrorCode.RATE_LIMITED, 429)
    grant = Grant.objects.filter(pairing_code=code, channel=Grant.IN_PERSON).first()
    if grant_state(grant) != "pending":
        return fail(ErrorCode.PAIRING_UNAVAILABLE, 404)
    return ok({"recipient_key": grant.recipient_key})


def parse_pairing_code(raw) -> tuple[str, str] | None:
    """``ABCD2345.0123456789abcdef`` -> (short code, key fingerprint), or None."""
    short_code, _, confirmation = (raw if isinstance(raw, str) else "").strip().partition(".")
    short_code, confirmation = short_code.upper(), confirmation.lower()
    if not CODE_PATTERN.fullmatch(short_code) or len(confirmation) != 16:
        return None
    return short_code, confirmation


def activate(grant: Grant, owner, key: str, keys: dict, minutes: int) -> None:
    grant.owner = owner
    grant.sender_key = key
    grant.expires_at = capped_expiry(timezone.now(), minutes)
    grant.save(update_fields=["owner", "sender_key", "expires_at"])
    attach(grant, keys)


@require_POST
@owner_required
def approve_in_person(request):
    body = json_body(request)
    parsed = parse_pairing_code(body.get("code"))
    if parsed is None:
        return fail(ErrorCode.INVALID_PAIRING_CODE, 400)
    if not allow_attempt(rate_key("grant", str(request.user.pk)), 24, 300):
        return fail(ErrorCode.RATE_LIMITED, 429)
    try:
        chosen = chosen_documents(body, request.user)
        key, keys = sender_key(body), sealed_keys(body, chosen)
        minutes = lifetime(body, IN_PERSON_MINUTES, settings.ACCESS_SECONDS // 60)
    except ShareError as error:
        return fail(error.code, 400)
    with transaction.atomic():
        grant = Grant.objects.select_for_update().filter(pairing_code=parsed[0], channel=Grant.IN_PERSON).first()
        if grant_state(grant) != "pending":
            return fail(ErrorCode.PAIRING_UNAVAILABLE, 409)
        if fingerprint(grant.recipient_key) != parsed[1]:
            return fail(ErrorCode.PAIRING_MISMATCH, 400)
        activate(grant, request.user, key, keys, minutes)
    record_event(grant, "approved", detail=f"{len(keys)} documento(s), {minutes} min")
    audit(request, "grant.approved", grant=grant.id, channel=grant.channel)
    return ok(grant_payload(grant), status=201)


@require_POST
@owner_required
def approve_request(request, grant_id):
    """Approve a podeabrir.com/@handle request after comparing the 6-digit code."""
    body = json_body(request)
    try:
        chosen = chosen_documents(body, request.user)
        key, keys = sender_key(body), sealed_keys(body, chosen)
        minutes = lifetime(body, IN_PERSON_MINUTES, settings.ACCESS_SECONDS // 60)
    except ShareError as error:
        return fail(error.code, 400)
    with transaction.atomic():
        grant = Grant.objects.select_for_update().filter(
            pk=grant_id, owner=request.user, channel=Grant.HANDLE,
        ).first()
        if grant_state(grant) != "pending":
            return fail(ErrorCode.PAIRING_UNAVAILABLE, 409)
        activate(grant, request.user, key, keys, minutes)
    record_event(grant, "approved", detail=f"{len(keys)} documento(s), {minutes} min")
    audit(request, "grant.approved", grant=grant.id, channel=grant.channel)
    return ok(grant_payload(grant), status=201)


def link_policy(body: dict, document_count: int) -> dict:
    minutes = lifetime(body, LINK_MINUTES)
    max_opens = body.get("max_opens")
    if max_opens is not None and (not isinstance(max_opens, int) or not 1 <= max_opens <= MAX_OPENS_LIMIT):
        raise ShareError(ErrorCode.INVALID_POLICY)
    pin = body.get("pin") or ""
    if pin and (not isinstance(pin, str) or not pin.isdigit() or not 4 <= len(pin) <= 8):
        raise ShareError(ErrorCode.INVALID_POLICY)
    if not pin and (minutes > 24 * 60 or document_count > 1):
        raise ShareError(ErrorCode.PIN_REQUIRED)
    label = body.get("label") or ""
    if not isinstance(label, str) or len(label) > 80:
        raise ShareError(ErrorCode.INVALID_POLICY)
    return {
        "expires_at": capped_expiry(timezone.now(), minutes), "max_opens": max_opens,
        "pin_verifier": make_password(pin) if pin else "", "label": label.strip(),
    }


@require_POST
@owner_required
def create_link(request):
    body = json_body(request)
    if not allow_attempt(rate_key("link", str(request.user.pk)), 30, 300):
        return fail(ErrorCode.RATE_LIMITED, 429)
    try:
        chosen = chosen_documents(body, request.user)
        keys = sealed_keys(body, chosen)
        policy = link_policy(body, len(chosen))
    except ShareError as error:
        return fail(error.code, 400)
    with transaction.atomic():
        grant = Grant.objects.create(channel=Grant.LINK, owner=request.user, **policy)
        attach(grant, keys)
    record_event(grant, "created", detail=f"{len(keys)} documento(s)")
    audit(request, "grant.link_created", grant=grant.id)
    return ok(grant_payload(grant), status=201)


@require_POST
@owner_required
def extend_grant(request, grant_id):
    try:
        minutes = lifetime(json_body(request), EXTEND_MINUTES)
    except ShareError as error:
        return fail(error.code, 400)
    with transaction.atomic():
        grant = Grant.objects.select_for_update().filter(pk=grant_id, owner=request.user).first()
        if grant is None or grant.ended_at or not grant.expires_at:
            return fail(ErrorCode.NOT_FOUND, 404)
        grant.expires_at = capped_expiry(max(grant.expires_at, timezone.now()), minutes)
        grant.save(update_fields=["expires_at"])
    record_event(grant, "extended", detail=f"+{minutes} min")
    return ok(grant_payload(grant))


@require_http_methods(["DELETE"])
@owner_required
def revoke_grant(request, grant_id):
    """Idempotent: ending an unknown or already ended grant is a no-op 204."""
    with transaction.atomic():
        grant = Grant.objects.select_for_update().filter(pk=grant_id, owner=request.user, ended_at__isnull=True).first()
        if grant is not None:
            end_grant(grant, "revoked")
    if grant is not None:
        record_event(grant, "ended", detail="encerrado por você")
        audit(request, "grant.revoked", grant=grant.id)
    return ok(status=204)
