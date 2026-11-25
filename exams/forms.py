"""Request validation for the JSON API (Django forms validate plain dicts)."""

from django import forms
from django.conf import settings

from .crypto_format import decode_token, sealed_blob, wrapped_key_bytes


class IdentityEmailField(forms.EmailField):
    """The account identity. Normalized because it also salts the browser key derivation."""

    def __init__(self, **kwargs):
        super().__init__(max_length=150, **kwargs)

    def clean(self, value):
        return super().clean(value.strip() if isinstance(value, str) else value).lower()


class OTPField(forms.RegexField):
    def __init__(self):
        super().__init__(r"^[0-9]{6}\Z")


class TokenField(forms.RegexField):
    """Raw single-use token from an emailed link."""

    def __init__(self):
        super().__init__(r"^[A-Za-z0-9_-]{43}\Z")


class DerivedSecretField(forms.CharField):
    """A 32-byte value derived in the browser (password credential or recovery proof)."""

    def __init__(self, **kwargs):
        super().__init__(max_length=43, **kwargs)

    def clean(self, value):
        value = super().clean(value)
        if value:
            try:
                decode_token(value, 32)
            except ValueError as error:
                raise forms.ValidationError("O navegador não preparou a autenticação.") from error
        return value


class WrappedKeyField(forms.CharField):
    """A key sealed in the browser (versioned AES-GCM envelope, 61 bytes)."""

    def __init__(self, **kwargs):
        super().__init__(max_length=82, **kwargs)

    def clean(self, value):
        value = super().clean(value)
        if value:
            try:
                wrapped_key_bytes(value)
            except ValueError as error:
                raise forms.ValidationError("Chave inválida.") from error
        return value


class SealedField(forms.CharField):
    """Metadata sealed in the browser with the document's data key."""

    def clean(self, value):
        value = super().clean(value)
        if value:
            try:
                sealed_blob(value, settings.SEALED_METADATA_MAX_BYTES)
            except ValueError as error:
                raise forms.ValidationError("Dado cifrado inválido.") from error
        return value


class LoginForm(forms.Form):
    email = IdentityEmailField()
    password = DerivedSecretField()
    otp = OTPField()


class VaultVerifyForm(forms.Form):
    password = DerivedSecretField()


class EmailForm(forms.Form):
    email = IdentityEmailField()


class InvitationTokenForm(forms.Form):
    token = TokenField()


class BootstrapInvitationForm(forms.Form):
    token = TokenField()
    email = IdentityEmailField()


class EnrollmentForm(forms.Form):
    token = TokenField()
    password = DerivedSecretField()
    wrapped_password = WrappedKeyField()
    wrapped_recovery = WrappedKeyField()
    recovery_proof = DerivedSecretField()


class ConfirmEnrollmentForm(forms.Form):
    otp = OTPField()


class PasswordResetForm(forms.Form):
    """mode=recovery keeps the vault (proof of the existing recovery code);
    mode=fresh discards it (new vault, new recovery code, reports deleted)."""

    token = TokenField()
    otp = OTPField()
    mode = forms.ChoiceField(choices=[("recovery", "recovery"), ("fresh", "fresh")])
    password = DerivedSecretField()
    wrapped_password = WrappedKeyField()
    recovery_proof = DerivedSecretField()
    wrapped_recovery = WrappedKeyField(required=False)

    def clean(self):
        data = super().clean()
        if data.get("mode") == "fresh" and not data.get("wrapped_recovery"):
            self.add_error("wrapped_recovery", "Obrigatório ao criar um novo cofre.")
        return data


class UploadForm(forms.Form):
    id = forms.UUIDField()
    sealed_title = SealedField(max_length=4096)
    sealed_issuer = SealedField(max_length=4096, required=False)
    document_date = forms.DateField(input_formats=["%Y-%m-%d"])
    wrapped_key = WrappedKeyField()
    ciphertext = forms.FileField()

    def clean_ciphertext(self):
        ciphertext = self.cleaned_data["ciphertext"]
        if not 34 <= ciphertext.size <= settings.SEALED_PDF_MAX_BYTES or ciphertext.read(1) != b"\x01":
            raise forms.ValidationError("Arquivo criptografado inválido ou acima do limite.")
        ciphertext.seek(0)
        return ciphertext


class HandleForm(forms.Form):
    """Personal address podeabrir.com/@handle."""

    handle = forms.RegexField(r"^[a-zA-Z0-9](?:[a-zA-Z0-9._-]{1,28}[a-zA-Z0-9])\Z", error_messages={
        "invalid": "Use de 3 a 30 letras minúsculas, números, ponto, hífen ou sublinhado.",
    })
    active = forms.BooleanField(required=False)

    def clean_handle(self):
        return self.cleaned_data["handle"].lower()


class LinkOpenForm(forms.Form):
    pin = forms.RegexField(r"^[0-9]{4,8}\Z", required=False)


class PushSubscriptionForm(forms.Form):
    endpoint = forms.URLField(max_length=500)
    p256dh = forms.RegexField(r"^[A-Za-z0-9_-]{80,100}\Z")
    auth = forms.RegexField(r"^[A-Za-z0-9_-]{16,40}\Z")
