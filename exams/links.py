"""Recipient side of a remote link: podeabrir.com/s/<id>#<link key>.

The link key lives only in the URL fragment, so the server never sees it. The server enforces
the policy: lifetime, number of opens, PIN (with lockout) and revocation. Content is released
only after an explicit "Abrir" (POST), so link-preview bots cannot consume a view.
"""

import time
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core import signing
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import LinkOpenForm
from .library import SUMMARY_FIELDS, document_summary, encrypted_response
from .models import Grant, GrantDocument
from .policy import browser_agent, end_grant, grant_state, record_event
from .push import notify_owner
from .responses import ErrorCode, fail, ok
from .security import allow_attempt, json_body, rate_key

SESSION_SALT = "podeabrir.link-session"


def session_cookie(grant_id) -> str:
    return f"link_{grant_id.hex[:16]}"


def link_grant(grant_id, lock=False):
    grants = Grant.objects.select_for_update() if lock else Grant.objects
    return grants.filter(pk=grant_id, channel=Grant.LINK).first()


def viewing_until(request, grant) -> float:
    """Seconds-since-epoch the current viewing session lasts, or 0 when there is none."""
    try:
        data = signing.loads(request.COOKIES.get(session_cookie(grant.id), ""), salt=SESSION_SALT)
    except signing.BadSignature:
        return 0
    return data["until"] if data.get("grant") == str(grant.id) else 0


def session_active(request, grant) -> bool:
    if grant is None or grant.ended_at or grant.expires_at <= timezone.now():
        return False
    return viewing_until(request, grant) > time.time()


@require_GET
def link_preview(request, grant_id):
    """Neutral page data. Unknown, ended and exhausted links all look the same."""
    grant = link_grant(grant_id)
    if grant_state(grant) != "active":
        return ok({"state": "unavailable"})
    return ok({
        "state": "available", "pin_required": bool(grant.pin_verifier), "label": grant.label,
        "document_count": grant.grantdocument_set.count(), "expires_at": grant.expires_at.isoformat(),
    })


def check_pin(request, grant, pin: str):
    """Returns an error response, or None when the PIN is fine. Too many failures lock the link."""
    if not grant.pin_verifier:
        return None
    if not pin:
        return fail(ErrorCode.INVALID_PIN, 403)
    if check_password(pin, grant.pin_verifier):
        return None
    grant.pin_failures += 1
    grant.save(update_fields=["pin_failures"])
    if grant.pin_failures >= settings.LINK_PIN_MAX_FAILURES:
        end_grant(grant, "locked")
        record_event(grant, "ended", detail="bloqueado: PIN incorreto")
        return fail(ErrorCode.LINK_UNAVAILABLE, 410)
    record_event(grant, "denied", agent=browser_agent(request), detail="PIN incorreto")
    return fail(ErrorCode.INVALID_PIN, 403)


@require_POST
def open_link(request, grant_id):
    form = LinkOpenForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.INVALID_PIN, 403)
    if not allow_attempt(rate_key("link-open", f"{grant_id}:{request.META.get('REMOTE_ADDR', '')}"), 10, 300):
        return fail(ErrorCode.RATE_LIMITED, 429)
    with transaction.atomic():
        grant = link_grant(grant_id, lock=True)
        if grant_state(grant) != "active":
            return fail(ErrorCode.LINK_UNAVAILABLE, 410)
        error = check_pin(request, grant, form.cleaned_data["pin"])
        if error:
            return error
        until = min(grant.expires_at.timestamp(), time.time() + settings.LINK_VIEW_MINUTES * 60)
        grant.opens += 1
        grant.viewing_until = max(grant.viewing_until or timezone.now(), datetime.fromtimestamp(until, dt_timezone.utc))
        grant.save(update_fields=["opens", "viewing_until"])
        shared = list(
            GrantDocument.objects.filter(grant=grant).select_related("document")
            .only("wrapped_key", *[f"document__{field}" for field in SUMMARY_FIELDS])
        )
    record_event(grant, "opened", agent=browser_agent(request), detail=f"abertura {grant.opens}")
    notify_owner(grant.owner, "Link aberto", "Alguém abriu um link que você compartilhou.", "/compartilhamentos/")
    response = ok({
        "label": grant.label, "expires_at": grant.expires_at.isoformat(), "view_until": int(until),
        "documents": [{**document_summary(item.document), "wrapped_key": item.wrapped_key} for item in shared],
    })
    response.set_cookie(
        session_cookie(grant.id), signing.dumps({"grant": str(grant.id), "until": until}, salt=SESSION_SALT),
        max_age=int(until - time.time()) + 1, path=f"/api/links/{grant.id}/",
        secure=not settings.DEBUG, httponly=True, samesite="Strict",
    )
    return response


@require_GET
def link_status(request, grant_id):
    return ok({"state": "active" if session_active(request, link_grant(grant_id)) else "ended"})


@require_GET
def link_document_content(request, grant_id, document_id):
    grant = link_grant(grant_id)
    if not session_active(request, grant):
        return HttpResponse(status=403)
    shared = (
        GrantDocument.objects.filter(grant=grant, document_id=document_id, document__owner_id=grant.owner_id)
        .values_list("document__ciphertext", "wrapped_key").first()
    )
    if shared is None:
        return HttpResponse(status=404)
    record_event(grant, "viewed", document=str(document_id), agent=browser_agent(request))
    return encrypted_response(*shared)
