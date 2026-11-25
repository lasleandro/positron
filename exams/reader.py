"""Reader screen ("Ler documentos"): in-person QR pairing and podeabrir.com/@nome requests.

The reader has no account. Its browser is identified by an HttpOnly cookie and holds an
ephemeral ECDH key pair; the owner re-seals the chosen data keys for that public key.
"""

import logging
import re
import secrets
from datetime import timedelta
from hashlib import sha256

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from .crypto_format import fingerprint, public_key_bytes
from .library import document_summary, encrypted_response
from .models import EmailDelivery, Grant, GrantDocument, OwnerProfile
from .outbox import enqueue
from .policy import browser_agent, grant_state, is_active_reader_grant, record_event
from .push import notify_owner
from .qr import qr_data_uri
from .responses import ErrorCode, fail, ok
from .security import allow_attempt, json_body, rate_key

logger = logging.getLogger("exams.outbox")
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_PATTERN = re.compile(f"[{CODE_ALPHABET}]{{8}}")
HANDLE_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9._-]{1,28}[a-z0-9])")


def browser_digest(request):
    token = request.COOKIES.get(settings.READER_COOKIE_NAME, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    return sha256(token.encode()).hexdigest()


def reader_grant(request):
    digest = browser_digest(request)
    return Grant.objects.filter(browser_digest=digest).exclude(channel=Grant.LINK).first() if digest else None


def key_salt(grant) -> str:
    """HKDF salt both sides use for the ECDH-derived key."""
    return grant.pairing_code if grant.channel == Grant.IN_PERSON else grant.nonce


def reader_payload(grant) -> dict:
    state = grant_state(grant)
    payload = {"state": state, "channel": grant.channel if grant else None}
    if state == "pending" and grant.channel == Grant.IN_PERSON:
        pairing = grant.pairing_code + "." + fingerprint(grant.recipient_key)
        payload.update(
            code=pairing, qr=qr_data_uri(f"{settings.ORIGIN}/autorizar/#{pairing}"),
            pair_until=grant.pair_until.isoformat(),
        )
    elif state == "pending":
        payload.update(nonce=grant.nonce, pair_until=grant.pair_until.isoformat())
    elif state == "active":
        shared = GrantDocument.objects.filter(grant=grant, document__owner_id=grant.owner_id).select_related("document")
        payload.update(
            grant=str(grant.id),  # shown as "Ref." in the watermark, traceable in the owner's list
            salt=key_salt(grant), sender_key=grant.sender_key, expires_at=grant.expires_at.isoformat(),
            documents=[{**document_summary(item.document), "wrapped_key": item.wrapped_key} for item in shared],
        )
    return payload


def handle_owner(handle: str):
    profile = OwnerProfile.objects.filter(handle=handle, handle_active=True).select_related("user").first()
    return profile.user if profile and profile.user.is_active else None


def create_reader_grant(recipient_key: str, handle: str | None) -> tuple[Grant | None, str]:
    """Pending grant bound to a fresh browser token. Unknown handles get an ownerless grant that
    behaves identically and simply expires, so the page never reveals whether @handle exists."""
    token = secrets.token_urlsafe(32)
    common = {
        "browser_digest": sha256(token.encode()).hexdigest(), "recipient_key": recipient_key,
        "pair_until": timezone.now() + timedelta(seconds=settings.PAIR_SECONDS),
    }
    if handle is not None:
        grant = Grant.objects.create(
            channel=Grant.HANDLE, owner=handle_owner(handle), nonce=secrets.token_hex(8), **common,
        )
        return grant, token
    for _ in range(5):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        try:
            return Grant.objects.create(channel=Grant.IN_PERSON, pairing_code=code, **common), token
        except IntegrityError:
            continue
    return None, token


def announce_request(grant) -> None:
    """Tell the owner someone is waiting (email + push). Never reveals anything to the reader.

    Best effort: the request is already saved and visible in the owner's app, so a notification
    failure is logged and must not cost the reader the response (and its session cookie)."""
    if grant.owner_id is None:
        return
    record_event(grant, "requested")
    try:
        if allow_attempt(rate_key("request-mail", str(grant.owner_id)), 1, 300):
            enqueue(EmailDelivery.READ_REQUEST, grant.owner.username, user=grant.owner)
        notify_owner(grant.owner, "Pedido de leitura", "Alguém quer ler seus documentos agora.", "/compartilhamentos/")
    except Exception:
        logger.exception("read request notification failed for grant %s", grant.id)


def request_access(request):
    current = reader_grant(request)
    if grant_state(current) in {"pending", "active"}:
        return ok(reader_payload(current))
    body = json_body(request)
    handle = body.get("handle")
    if handle is not None and (not isinstance(handle, str) or not HANDLE_PATTERN.fullmatch(handle.lower())):
        handle = ""  # malformed: same treatment as unknown
    handle = handle.lower() if isinstance(handle, str) else None
    limit_key = rate_key("handle", handle) if handle is not None else "pair"
    if not allow_attempt("pair", 100, settings.PAIR_SECONDS) or not allow_attempt(limit_key, 10, settings.PAIR_SECONDS):
        return fail(ErrorCode.PAIRING_CAPACITY, 429)
    recipient_key = body.get("recipient_key", "")
    try:
        public_key_bytes(recipient_key if isinstance(recipient_key, str) else "")
    except ValueError:
        return fail(ErrorCode.INVALID_RECIPIENT_KEY, 400)

    grant, token = create_reader_grant(recipient_key, handle)
    if grant is None:
        return fail(ErrorCode.PAIRING_CAPACITY, 503)
    if grant.channel == Grant.HANDLE:
        announce_request(grant)
    response = ok(reader_payload(grant), status=201)
    response.set_cookie(
        settings.READER_COOKIE_NAME, token,
        max_age=settings.PAIR_SECONDS + settings.GRANT_MAX_MINUTES * 60,
        secure=not settings.DEBUG, httponly=True, samesite="Strict",
    )
    return response


@require_http_methods(["GET", "POST"])
def reader(request):
    if request.method == "POST":
        return request_access(request)
    return ok(reader_payload(reader_grant(request)))


@require_GET
def reader_status(request):
    return ok({"state": grant_state(reader_grant(request))})


@require_GET
def reader_document_content(request, document_id):
    grant = reader_grant(request)
    if not is_active_reader_grant(grant):
        return HttpResponse(status=403)
    shared = (
        GrantDocument.objects.filter(grant=grant, document_id=document_id, document__owner_id=F("grant__owner_id"))
        .values_list("document__ciphertext", "wrapped_key").first()
    )
    if shared is None:
        return HttpResponse(status=404)
    record_event(grant, "opened", document=str(document_id), agent=browser_agent(request))
    return encrypted_response(*shared)
