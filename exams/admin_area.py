"""Admin area (staff only): invitations sent, access requests received and who is an admin."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from .models import AccessRequest, EmailDelivery, Invitation
from .responses import ErrorCode, fail, ok
from .security import allow_attempt, audit, json_body, rate_key, staff_required

User = get_user_model()
PAGE_SIZE = 50
PENDING_DELIVERY = {"queued", "processing", "retry_wait"}


def paged(request, queryset, serialize):
    """``{items, page, has_more}`` for ``?page=`` (from 1), PAGE_SIZE rows at a time."""
    page = request.GET.get("page", "1")
    if not page.isdigit() or int(page) < 1:
        return fail(ErrorCode.VALIDATION_FAILED, 400)
    page = int(page)
    rows = list(queryset[(page - 1) * PAGE_SIZE: page * PAGE_SIZE + 1])
    return ok({"items": serialize(rows[:PAGE_SIZE]), "page": page, "has_more": len(rows) > PAGE_SIZE})


def existing_accounts(emails) -> set[str]:
    return set(User.objects.filter(username__in=set(emails)).values_list("username", flat=True))


def invitation_status(delivery, accounts: set[str], open_invites: set[str]) -> str:
    """account | queued | bounced | failed | expired | sent."""
    if delivery.to_address in accounts:
        return "account"
    if delivery.status == "bounced":
        return "bounced"
    if delivery.status in PENDING_DELIVERY:
        return "queued"
    if delivery.status != "sent":
        return "failed"
    return "sent" if delivery.to_address in open_invites else "expired"


@require_GET
@staff_required
def admin_invitations(request):
    """Invitation emails, newest first, with how far each one got."""
    def serialize(rows):
        emails = [row.to_address for row in rows]
        accounts = existing_accounts(emails)
        open_invites = set(
            Invitation.objects.filter(email__in=emails, used_at__isnull=True, expires_at__gt=timezone.now())
            .values_list("email", flat=True)
        )
        return [{
            "id": str(row.id), "email": row.to_address, "admin": row.grants_staff,
            "created_at": row.created_at.isoformat(), "status": invitation_status(row, accounts, open_invites),
            "bounce_code": row.last_error_code.removeprefix("dsn:") if row.status == "bounced" else "",
        } for row in rows]

    deliveries = EmailDelivery.objects.filter(purpose=EmailDelivery.INVITATION).order_by("-created_at")
    return paged(request, deliveries, serialize)


@require_GET
@staff_required
def admin_access_requests(request):
    """"Solicitar conta" messages, newest first: new, invited or already with an account."""
    def serialize(rows):
        emails = [row.email for row in rows]
        accounts = existing_accounts(emails)
        invited = set(EmailDelivery.objects.filter(purpose=EmailDelivery.INVITATION, to_address__in=emails)
                      .values_list("to_address", flat=True))
        return [{
            "id": row.id, "email": row.email, "name": row.name, "message": row.message,
            "created_at": row.created_at.isoformat(),
            "status": "account" if row.email in accounts else "invited" if row.email in invited else "new",
        } for row in rows]

    return paged(request, AccessRequest.objects.order_by("-created_at", "-id"), serialize)


def user_payload(user, request) -> dict:
    return {
        "id": user.pk, "email": user.username, "is_staff": user.is_staff, "is_self": user.pk == request.user.pk,
        "date_joined": user.date_joined.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


@require_GET
@staff_required
def admin_users(request):
    """Accounts, newest first."""
    users = User.objects.order_by("-date_joined", "-id")
    return paged(request, users, lambda rows: [user_payload(user, request) for user in rows])


@require_http_methods(["PATCH"])
@staff_required
def admin_user(request, user_id: int):
    """Grant or remove the admin role. Nobody changes their own role: no lock-out, no self-escalation."""
    is_staff = json_body(request).get("is_staff")
    if not isinstance(is_staff, bool):
        return fail(ErrorCode.VALIDATION_FAILED, 400)
    if user_id == request.user.pk:
        return fail(ErrorCode.CANNOT_CHANGE_OWN_ROLE, 400)
    if not allow_attempt(rate_key("admin-role", str(request.user.pk)), 30, 300):
        return fail(ErrorCode.RATE_LIMITED, 429)
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=user_id).first()
        if user is None:
            return fail(ErrorCode.NOT_FOUND, 404)
        user.is_staff = is_staff
        user.save(update_fields=["is_staff"])
    audit(request, "admin.role_changed", target=user.pk, is_staff=is_staff)
    return ok(user_payload(user, request))
