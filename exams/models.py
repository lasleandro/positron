from uuid import uuid4

from django.conf import settings
from django.db import models


class Document(models.Model):
    """A sensitive document (medical exam, contract, statement, ...). Everything but the date is
    sealed in the owner's browser: the PDF with a random data key, title/issuer with the same key
    (AAD "meta-title:<id>" / "meta-issuer:<id>"), the data key with the vault key."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    sealed_title = models.TextField()
    sealed_issuer = models.TextField(blank=True)
    document_date = models.DateField()
    ciphertext = models.BinaryField(editable=False)
    wrapped_key = models.CharField(max_length=82)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-document_date", "-uploaded_at"]


class Grant(models.Model):
    """A short-lived permission to read a set of documents, whatever the channel."""

    IN_PERSON = "in_person"  # reader screen shows a QR, owner scans it
    LINK = "link"            # owner sends a link; the key travels in the URL fragment
    HANDLE = "handle"        # reader opens podeabrir.com/@nome, owner approves a request
    CHANNELS = [(IN_PERSON, IN_PERSON), (LINK, LINK), (HANDLE, HANDLE)]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    channel = models.CharField(max_length=16, choices=CHANNELS)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True)
    browser_digest = models.CharField(max_length=64, null=True, unique=True)
    pairing_code = models.CharField(max_length=8, null=True, unique=True)
    nonce = models.CharField(max_length=16, blank=True)
    recipient_key = models.CharField(max_length=87, blank=True)
    sender_key = models.CharField(max_length=87, blank=True)
    label = models.CharField(max_length=80, blank=True)
    pair_until = models.DateTimeField(null=True, db_index=True)
    expires_at = models.DateTimeField(null=True, db_index=True)
    max_opens = models.PositiveIntegerField(null=True)
    opens = models.PositiveIntegerField(default=0)
    viewing_until = models.DateTimeField(null=True)  # end of the latest link reading session
    pin_verifier = models.CharField(max_length=128, blank=True)
    pin_failures = models.PositiveSmallIntegerField(default=0)
    ended_at = models.DateTimeField(null=True)
    end_reason = models.CharField(max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    documents = models.ManyToManyField(Document, through="GrantDocument", related_name="grants")


class GrantDocument(models.Model):
    """The document's data key, re-sealed in the owner's browser for this grant only."""

    grant = models.ForeignKey(Grant, on_delete=models.CASCADE)
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    wrapped_key = models.CharField(max_length=82)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["grant", "document"], name="unique_grant_document")]


class GrantEvent(models.Model):
    """Append-only "quem viu" history, hash-chained per owner so the browser can detect edits."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    grant = models.ForeignKey(Grant, on_delete=models.SET_NULL, null=True)
    channel = models.CharField(max_length=16)
    kind = models.CharField(max_length=16)
    document = models.CharField(max_length=36, blank=True)
    agent = models.CharField(max_length=40, blank=True)
    detail = models.CharField(max_length=120, blank=True)
    at = models.DateTimeField()
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["id"]


class OwnerProfile(models.Model):
    """Optional personal address podeabrir.com/@handle (opt-in)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    handle = models.CharField(max_length=30, null=True, unique=True)
    handle_active = models.BooleanField(default=False)


class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=100)
    auth = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)


class SecurityState(models.Model):
    name = models.CharField(primary_key=True, max_length=32)
    bucket = models.BigIntegerField(default=0)
    count = models.PositiveIntegerField(default=0)


class AccountMFA(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    encrypted_secret = models.TextField()
    last_otp_step = models.BigIntegerField(default=-1)


class Invitation(models.Model):
    """Single-use sign-up link, bound to the email address it was sent to."""

    digest = models.CharField(primary_key=True, max_length=64)
    email = models.EmailField(max_length=150, db_index=True)
    grants_staff = models.BooleanField(default=False)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True)


class AccountVault(models.Model):
    """The random vault key, sealed in the browser twice: by the password and by the recovery code.

    The server cannot open either copy. ``recovery_verifier`` is a password hash of a value
    derived from the recovery code, so a reset can prove possession without revealing it.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    wrapped_password = models.CharField(max_length=82)
    wrapped_recovery = models.CharField(max_length=82)
    recovery_verifier = models.CharField(max_length=128)


class PasswordResetToken(models.Model):
    """Digest-only, single-use password reset link."""

    digest = models.CharField(primary_key=True, max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True)


class ConsentRecord(models.Model):
    """Acceptance of the Terms + Privacy Policy, including specific consent for sensitive data
    (LGPD art. 11, I), for one published version. A new version requires a new acceptance."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    version = models.CharField(max_length=20)
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "version"], name="unique_consent_version")]


class AccessRequest(models.Model):
    """"Solicitar acesso" from the login page, forwarded to the team (no self-signup yet)."""

    email = models.EmailField(max_length=150)
    name = models.CharField(max_length=120, blank=True)
    message = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class EmailDelivery(models.Model):
    """Durable outbox row. Raw tokens are never stored: they are issued when the message is rendered."""

    INVITATION = "invitation"
    PASSWORD_RESET = "password_reset"
    PASSWORD_CHANGED = "password_changed"
    READ_REQUEST = "read_request"
    ACCESS_REQUEST = "access_request"
    PURPOSES = [(name, name) for name in (INVITATION, PASSWORD_RESET, PASSWORD_CHANGED, READ_REQUEST, ACCESS_REQUEST)]
    STATUSES = [(name, name) for name in ("queued", "processing", "retry_wait", "sent", "failed", "suppressed", "bounced")]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    purpose = models.CharField(max_length=32, choices=PURPOSES)
    to_address = models.EmailField(max_length=150)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True)
    access_request = models.ForeignKey(AccessRequest, on_delete=models.CASCADE, null=True)
    grants_staff = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=STATUSES, default="queued", db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True)
    last_error_code = models.CharField(max_length=40, blank=True)
    sent_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
