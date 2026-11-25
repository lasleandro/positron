"""Owner session endpoints: session bootstrap, login, logout, vault password check."""

from django.conf import settings
from django.contrib.auth import login, logout
from django.db import connection
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET, require_POST

from .forms import LoginForm, VaultVerifyForm
from .models import AccountVault, ConsentRecord
from .policy import EXTEND_MINUTES, IN_PERSON_MINUTES, LINK_MINUTES, MAX_OPENS_LIMIT
from .responses import ErrorCode, fail, form_errors, ok
from .security import allow_attempt, audit, json_body, owner_required, rate_key, verify_owner


def session_payload(request) -> dict:
    """Everything the SPA needs before rendering: identity, CSRF token and product limits."""
    user = request.user
    return {
        "user": {
            "email": user.username, "is_staff": user.is_staff,
            "consent_ok": ConsentRecord.objects.filter(user=user, version=settings.LEGAL_VERSION).exists(),
        } if user.is_authenticated else None,
        "legal_version": settings.LEGAL_VERSION,
        "csrf_token": get_token(request),
        "vault_namespace": settings.VAULT_NAMESPACE,
        "limits": {
            "pdf_max_bytes": settings.PDF_MAX_BYTES,
            "pair_minutes": settings.PAIR_SECONDS // 60,
            "access_minutes": settings.ACCESS_SECONDS // 60,
            "invitation_hours": settings.INVITATION_HOURS,
            "in_person_minutes": list(IN_PERSON_MINUTES),
            "link_minutes": list(LINK_MINUTES),
            "extend_minutes": list(EXTEND_MINUTES),
            "max_opens": MAX_OPENS_LIMIT,
            "link_view_minutes": settings.LINK_VIEW_MINUTES,
        },
    }


def wrapped_vault(user) -> str:
    """The vault key sealed by the password-derived key; only the browser can open it."""
    return AccountVault.objects.get(user=user).wrapped_password


def start_owner_session(request, user) -> None:
    login(request, user)
    request.session.set_expiry(settings.OWNER_SESSION_SECONDS)


@require_GET
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return HttpResponse("ok", content_type="text/plain")


@require_GET
def session(request):
    return ok(session_payload(request))


@require_POST
def owner_login(request):
    form = LoginForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    email = form.cleaned_data["email"]
    if not allow_attempt("login", 100, 300) or not allow_attempt(rate_key("login", email), 12, 300):
        return fail(ErrorCode.RATE_LIMITED, 429)
    user = verify_owner(request, **form.cleaned_data)
    if user is None:
        audit(request, "auth.login_failed")
        return fail(ErrorCode.INVALID_CREDENTIALS, 401)
    start_owner_session(request, user)
    audit(request, "auth.login")
    return ok({**session_payload(request), "wrapped_vault": wrapped_vault(user)})


@require_POST
@owner_required
def verify_vault_password(request):
    if not allow_attempt(rate_key("vault", str(request.user.pk)), 12, 300):
        return fail(ErrorCode.RATE_LIMITED, 429)
    form = VaultVerifyForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400)
    if not request.user.check_password(form.cleaned_data["password"]):
        return fail(ErrorCode.INVALID_VAULT_PASSWORD, 401)
    return ok({"wrapped_vault": wrapped_vault(request.user)})


@require_POST
def owner_logout(request):
    if request.user.is_authenticated:
        audit(request, "auth.logout")
    logout(request)
    return ok(session_payload(request))


@require_POST
@owner_required
def accept_consent(request):
    """Record acceptance of the current Terms + Privacy Policy (consent gate, policy updates)."""
    from .forms import ConsentForm

    form = ConsentForm(json_body(request))
    if not form.is_valid() or form.cleaned_data["version"] != settings.LEGAL_VERSION:
        return fail(ErrorCode.VALIDATION_FAILED, 400)
    ConsentRecord.objects.get_or_create(user=request.user, version=settings.LEGAL_VERSION)
    audit(request, "consent.accepted", version=settings.LEGAL_VERSION)
    return ok(session_payload(request))
