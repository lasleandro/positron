import json
import logging
import time
from functools import wraps
from hashlib import sha256

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils.crypto import constant_time_compare

from .responses import ErrorCode, fail

audit_logger = logging.getLogger("exams.audit")


class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            body_size = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            body_size = 0
        if body_size > settings.SEALED_PDF_MAX_BYTES + settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
            response = fail(ErrorCode.PAYLOAD_TOO_LARGE, 413)
        else:
            response = self.get_response(request)
        response["Cache-Control"] = "no-store, private"
        response["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; "
            "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
            "worker-src 'self'; manifest-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response


def mfa_cipher():
    try:
        return Fernet(settings.TOTP_ENCRYPTION_KEY)
    except ValueError as error:
        raise ImproperlyConfigured("Configure uma chave Fernet válida em TOTP_ENCRYPTION_KEY.") from error


RATE_KEY_MAX = 32  # SecurityState.name max_length


def rate_key(purpose, identifier):
    """``purpose-<hash>`` sized to fit SecurityState.name; the hash keeps at least 64 bits."""
    digest_length = RATE_KEY_MAX - len(purpose) - 1
    if digest_length < 16:
        raise ValueError(f"rate-limit purpose too long: {purpose}")
    return purpose + "-" + sha256(identifier.encode()).hexdigest()[:digest_length]


def matching_otp_step(secret, otp):
    step = int(time.time()) // 30
    authenticator = pyotp.TOTP(secret)
    for candidate in (step, step - 1, step + 1):
        if constant_time_compare(authenticator.generate_otp(candidate), otp):
            return candidate
    return None


def owner_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return fail(ErrorCode.AUTH_REQUIRED, 401)
        return view(request, *args, **kwargs)

    return wrapped


def staff_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            return fail(ErrorCode.FORBIDDEN, 403)
        return view(request, *args, **kwargs)

    return owner_required(wrapped)


def json_body(request) -> dict:
    """Parse a JSON object body; anything else becomes an empty dict (forms then reject it)."""
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def audit(request, action: str, **fields) -> None:
    """Record a state-changing operation: who (user id), what, from where. Never log secrets."""
    who = request.user.pk if request.user.is_authenticated else "-"
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    audit_logger.info("%s user=%s ip=%s %s", action, who, request.META.get("REMOTE_ADDR", "-"), details)


@transaction.atomic
def allow_attempt(name, limit, window_seconds):
    from .models import SecurityState

    bucket = int(time.time()) // window_seconds
    state, _ = SecurityState.objects.select_for_update().get_or_create(name=name)
    if bucket != state.bucket:
        state.bucket = bucket
        state.count = 0
    if state.count >= limit:
        return False
    state.count += 1
    state.save(update_fields=["bucket", "count"])
    return True


def consume_otp(user, otp: str) -> bool:
    """Accept a TOTP code once: a step at or before the last accepted one is a replay."""
    from .models import AccountMFA

    with transaction.atomic():
        account = AccountMFA.objects.select_for_update().filter(user=user).first()
        if not account:
            return False
        try:
            secret = mfa_cipher().decrypt(account.encrypted_secret.encode()).decode()
        except InvalidToken:
            return False
        candidate = matching_otp_step(secret, otp)
        if candidate is None or candidate <= account.last_otp_step:
            return False
        account.last_otp_step = candidate
        account.save(update_fields=["last_otp_step"])
    return True


def verify_owner(request, email, password, otp):
    user = authenticate(request, username=email, password=password)
    if user is None or not consume_otp(user, otp):
        return None
    return user
