"""Invitation-only sign-up. Invitations are emailed and bound to that address (proof of ownership).

The first account uses the installation (bootstrap) code to email an invitation to itself;
every other account is invited by a staff member.
"""

import time

import pyotp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.http import require_POST

from .account import session_payload, start_owner_session, wrapped_vault
from .forms import BootstrapInvitationForm, ConfirmEnrollmentForm, EmailForm, EnrollmentForm, InvitationTokenForm
from .models import AccountMFA, AccountVault, EmailDelivery, Invitation, SecurityState
from .outbox import enqueue, token_digest
from .qr import qr_data_uri
from .responses import ErrorCode, fail, form_errors, ok
from .security import allow_attempt, audit, json_body, matching_otp_step, mfa_cipher, rate_key, staff_required

User = get_user_model()
ENROLL_KEY = "pending_enrollment"
MAX_OTP_ATTEMPTS = 8


def find_invite(digest, lock=False):
    invitations = Invitation.objects.select_for_update() if lock else Invitation.objects
    return invitations.filter(pk=digest, used_at__isnull=True, expires_at__gt=timezone.now()).first()


def is_bootstrap(digest):
    return bool(settings.BOOTSTRAP_INVITE_DIGEST) and constant_time_compare(digest, settings.BOOTSTRAP_INVITE_DIGEST)


def allow_email_to(email: str) -> bool:
    return allow_attempt(rate_key("mail", email), settings.EMAIL_MAX_SENDS_PER_HOUR, 3600)


def authenticator_setup(secret: str, email: str) -> dict:
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Pode Abrir")
    return {"email": email, "qr": qr_data_uri(uri), "secret": secret}


@require_POST
@staff_required
def create_invitation(request):
    form = EmailForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    email = form.cleaned_data["email"]
    if not allow_attempt(rate_key("invite", str(request.user.pk)), 10, 300) or not allow_email_to(email):
        return fail(ErrorCode.RATE_LIMITED, 429)
    if User.objects.filter(username=email).exists():
        return fail(ErrorCode.USERNAME_TAKEN, 409)
    enqueue(EmailDelivery.INVITATION, email)
    audit(request, "invitation.queued")
    return ok({"email": email}, status=202)


@require_POST
def bootstrap_invitation(request):
    """Installation code -> invitation emailed to the first (staff) account. Works until one account exists."""
    form = BootstrapInvitationForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    if not allow_attempt("bootstrap", 10, 300):
        return fail(ErrorCode.RATE_LIMITED, 429)
    if not is_bootstrap(token_digest(form.cleaned_data["token"])) or User.objects.exists():
        return fail(ErrorCode.INVALID_INVITE, 400)
    email = form.cleaned_data["email"]
    if not allow_email_to(email):
        return fail(ErrorCode.RATE_LIMITED, 429)
    enqueue(EmailDelivery.INVITATION, email, grants_staff=True)
    audit(request, "invitation.bootstrap_queued")
    return ok({"email": email}, status=202)


@require_POST
def inspect_invitation(request):
    """Tell the sign-up page which address an invitation link belongs to."""
    form = InvitationTokenForm(json_body(request))
    if not form.is_valid() or not allow_attempt("invite-inspect", 60, 300):
        return fail(ErrorCode.INVALID_INVITE, 400)
    invitation = find_invite(token_digest(form.cleaned_data["token"]))
    if invitation is None:
        return fail(ErrorCode.INVALID_INVITE, 400)
    return ok({"email": invitation.email})


@require_POST
def enroll(request):
    if request.user.is_authenticated:
        return fail(ErrorCode.FORBIDDEN, 403)
    form = EnrollmentForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    if not allow_attempt("enrollment", 30, 300):
        return fail(ErrorCode.RATE_LIMITED, 429)
    data = form.cleaned_data
    digest = token_digest(data["token"])
    invitation = find_invite(digest)
    if invitation is None:
        return fail(ErrorCode.INVALID_INVITE, 400)
    if User.objects.filter(username=invitation.email).exists():
        return fail(ErrorCode.USERNAME_TAKEN, 409)

    secret = pyotp.random_base32()
    request.session.cycle_key()
    request.session[ENROLL_KEY] = {
        "digest": digest,
        "email": invitation.email,
        "password_hash": make_password(data["password"]),
        "wrapped_password": data["wrapped_password"],
        "wrapped_recovery": data["wrapped_recovery"],
        "recovery_verifier": make_password(data["recovery_proof"]),
        "secret": mfa_cipher().encrypt(secret.encode()).decode(),
        "expires": int(time.time()) + settings.ENROLLMENT_SECONDS,
        "attempts": 0,
    }
    return ok(authenticator_setup(secret, invitation.email), status=201)


@transaction.atomic
def register_account(pending, step):
    invitation = find_invite(pending["digest"], lock=True)
    if invitation is None or invitation.email != pending["email"]:
        return None
    if invitation.grants_staff:
        # Serialize bootstrap: only the very first account may become staff this way.
        SecurityState.objects.select_for_update().get_or_create(name="bootstrap")
        if User.objects.exists():
            return None
    user = User.objects.create(
        username=pending["email"], email=pending["email"],
        password=pending["password_hash"], is_staff=invitation.grants_staff,
    )
    AccountMFA.objects.create(user=user, encrypted_secret=pending["secret"], last_otp_step=step)
    AccountVault.objects.create(
        user=user, wrapped_password=pending["wrapped_password"],
        wrapped_recovery=pending["wrapped_recovery"], recovery_verifier=pending["recovery_verifier"],
    )
    invitation.used_at = timezone.now()
    invitation.save(update_fields=["used_at"])
    return user


@require_POST
def confirm_enrollment(request):
    if request.user.is_authenticated:
        return fail(ErrorCode.FORBIDDEN, 403)
    pending = request.session.get(ENROLL_KEY)
    if not pending or pending["expires"] <= time.time():
        request.session.pop(ENROLL_KEY, None)
        return fail(ErrorCode.ENROLLMENT_EXPIRED, 410)
    form = ConfirmEnrollmentForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    if not allow_attempt("enroll-mfa", 60, 300):
        return fail(ErrorCode.RATE_LIMITED, 429)
    if pending["attempts"] >= MAX_OTP_ATTEMPTS:
        request.session.pop(ENROLL_KEY)
        return fail(ErrorCode.ENROLLMENT_EXPIRED, 410)

    pending["attempts"] += 1
    request.session[ENROLL_KEY] = pending
    secret = mfa_cipher().decrypt(pending["secret"].encode()).decode()
    step = matching_otp_step(secret, form.cleaned_data["otp"])
    if step is None:
        return fail(ErrorCode.INVALID_OTP, 400)
    try:
        user = register_account(pending, step)
    except IntegrityError:
        user = None
    request.session.pop(ENROLL_KEY, None)
    if user is None:
        return fail(ErrorCode.ENROLLMENT_UNAVAILABLE, 409)
    start_owner_session(request, user)
    audit(request, "account.created", staff=user.is_staff)
    return ok({**session_payload(request), "wrapped_vault": wrapped_vault(user)}, status=201)
