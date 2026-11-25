"""Email password reset that keeps end-to-end encryption.

The emailed link alone never unlocks anything. The browser also needs the TOTP code and either:
- mode=recovery: the recovery code, which opens the stored recovery copy of the vault key in the
  browser; the vault key is then re-sealed with the new password (reports preserved); or
- mode=fresh: the user declares the recovery code lost; a new vault replaces the old one and every
  report (unreadable without the old key) is deleted.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import EmailForm, InvitationTokenForm, PasswordResetForm
from .models import AccountVault, Document, EmailDelivery, Grant, PasswordResetToken
from .outbox import enqueue, token_digest
from .policy import end_grant
from .responses import ErrorCode, fail, form_errors, ok
from .security import allow_attempt, audit, consume_otp, json_body, rate_key

User = get_user_model()
GENERIC_REQUEST_REPLY = {"message": "Se existir uma conta para este email, você receberá as instruções."}


def find_token(raw: str, lock: bool = False):
    tokens = PasswordResetToken.objects.select_for_update() if lock else PasswordResetToken.objects
    return tokens.select_related("user").filter(
        pk=token_digest(raw), consumed_at__isnull=True, expires_at__gt=timezone.now(), user__is_active=True,
    ).first()


@require_POST
def request_reset(request):
    """Always the same answer, whether or not the account exists (no enumeration)."""
    form = EmailForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    email = form.cleaned_data["email"]
    if not allow_attempt("reset-request", 60, 300) or not allow_attempt(rate_key("mail", email), 5, 3600):
        return fail(ErrorCode.RATE_LIMITED, 429)
    user = User.objects.filter(username=email, is_active=True).first()
    if user is not None:
        enqueue(EmailDelivery.PASSWORD_RESET, email, user=user)
    audit(request, "auth.password_reset_requested", known=user is not None)
    return ok(GENERIC_REQUEST_REPLY, status=202)


@require_POST
def inspect_reset(request):
    """Return what the browser needs to rebuild the keys: the email (key salt) and the recovery copy."""
    form = InvitationTokenForm(json_body(request))
    if not form.is_valid() or not allow_attempt("reset-inspect", 60, 300):
        return fail(ErrorCode.INVALID_RESET_LINK, 400)
    token = find_token(form.cleaned_data["token"])
    if token is None:
        return fail(ErrorCode.INVALID_RESET_LINK, 400)
    vault = AccountVault.objects.get(user=token.user)
    return ok({"email": token.user.username, "wrapped_recovery": vault.wrapped_recovery})


def discard_vault_contents(user) -> None:
    """Old documents are undecryptable without the old vault key: end every grant and delete them."""
    for grant in Grant.objects.filter(owner=user, ended_at__isnull=True):
        end_grant(grant, "revoked")
    Document.objects.filter(owner=user).delete()


@require_POST
def confirm_reset(request):
    form = PasswordResetForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    data = form.cleaned_data
    with transaction.atomic():
        token = find_token(data["token"], lock=True)
        if token is None:
            return fail(ErrorCode.INVALID_RESET_LINK, 400)
        user = token.user
        if not allow_attempt(rate_key("reset", str(user.pk)), 8, 300):
            return fail(ErrorCode.RATE_LIMITED, 429)
        vault = AccountVault.objects.select_for_update().get(user=user)
        recovered = data["mode"] == "recovery"
        if not consume_otp(user, data["otp"]) or (
            recovered and not check_password(data["recovery_proof"], vault.recovery_verifier)
        ):
            audit(request, "auth.password_reset_rejected", user_id=user.pk)
            return fail(ErrorCode.INVALID_RECOVERY_CODE, 400)

        if not recovered:
            discard_vault_contents(user)
            vault.wrapped_recovery = data["wrapped_recovery"]
            vault.recovery_verifier = make_password(data["recovery_proof"])
        vault.wrapped_password = data["wrapped_password"]
        vault.save()
        # A new password hash also invalidates every existing session (Django session auth hash).
        user.set_password(data["password"])
        user.save(update_fields=["password"])
        PasswordResetToken.objects.filter(user=user, consumed_at__isnull=True).update(consumed_at=timezone.now())
        enqueue(EmailDelivery.PASSWORD_CHANGED, user.username, user=user)
    audit(request, "auth.password_reset_completed", user_id=user.pk, mode=data["mode"])
    return ok({"mode": data["mode"]})
