"""Owner settings: personal address (@handle), push subscriptions, and the "quem viu" history."""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.views.decorators.http import require_GET, require_http_methods

from .forms import HandleForm, PushSubscriptionForm
from .models import GrantEvent, OwnerProfile, PushSubscription
from .push import push_enabled
from .qr import qr_data_uri
from .responses import ErrorCode, fail, form_errors, ok
from .security import audit, json_body, owner_required


def profile_payload(profile: OwnerProfile) -> dict:
    address = f"{settings.ORIGIN}/@{profile.handle}" if profile.handle else ""
    return {
        "handle": profile.handle, "handle_active": profile.handle_active, "address": address,
        "address_qr": qr_data_uri(address) if address else "",
        "push_public_key": settings.VAPID_PUBLIC_KEY if push_enabled() else "",
    }


@require_http_methods(["GET", "PUT"])
@owner_required
def profile(request):
    current, _ = OwnerProfile.objects.get_or_create(user=request.user)
    if request.method == "GET":
        return ok(profile_payload(current))
    form = HandleForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    current.handle = form.cleaned_data["handle"]
    current.handle_active = form.cleaned_data["active"]
    try:
        with transaction.atomic():
            current.save(update_fields=["handle", "handle_active"])
    except IntegrityError:
        return fail(ErrorCode.HANDLE_TAKEN, 409)
    audit(request, "profile.handle_updated", active=current.handle_active)
    return ok(profile_payload(current))


@require_http_methods(["POST", "DELETE"])
@owner_required
def push_subscription(request):
    body = json_body(request)
    if request.method == "DELETE":
        PushSubscription.objects.filter(user=request.user, endpoint=body.get("endpoint", "")).delete()
        return ok(status=204)
    form = PushSubscriptionForm(body)
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    data = form.cleaned_data
    PushSubscription.objects.update_or_create(
        endpoint=data["endpoint"], defaults={"user": request.user, "p256dh": data["p256dh"], "auth": data["auth"]},
    )
    return ok(status=204)


def event_payload(event: GrantEvent) -> dict:
    return {
        "id": event.id, "grant": str(event.grant_id) if event.grant_id else "", "channel": event.channel,
        "kind": event.kind, "document": event.document, "agent": event.agent, "detail": event.detail,
        "at": event.at.isoformat(), "prev_hash": event.prev_hash, "hash": event.hash,
    }


@require_GET
@owner_required
def history(request):
    """The most recent window of the owner's chain, oldest first, so the browser can re-hash it."""
    recent = list(GrantEvent.objects.filter(owner=request.user).order_by("-id")[:settings.HISTORY_WINDOW])
    recent.reverse()
    return ok({"events": [event_payload(event) for event in recent],
               "total": GrantEvent.objects.filter(owner=request.user).count()})
