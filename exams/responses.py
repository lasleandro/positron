"""JSON envelope and error catalogue shared by every API view.

Every response body is ``{"data": ..., "error": null}`` on success or
``{"data": null, "error": {"code": ..., "message": ..., "fields": {...}}}``
on failure. Messages are user-facing (pt-BR) and never carry internal state.
"""

from enum import Enum

from django.http import HttpResponse, JsonResponse


class ErrorCode(str, Enum):
    AUTH_REQUIRED = "auth_required"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_VAULT_PASSWORD = "invalid_vault_password"
    RATE_LIMITED = "rate_limited"
    VALIDATION_FAILED = "validation_failed"
    INVALID_INVITE = "invalid_invite"
    USERNAME_TAKEN = "username_taken"
    ENROLLMENT_EXPIRED = "enrollment_expired"
    INVALID_OTP = "invalid_otp"
    ENROLLMENT_UNAVAILABLE = "enrollment_unavailable"
    STORE_FAILED = "store_failed"
    INVALID_PAIRING_CODE = "invalid_pairing_code"
    PAIRING_UNAVAILABLE = "pairing_unavailable"
    PAIRING_MISMATCH = "pairing_mismatch"
    NO_EXAMS_SELECTED = "no_exams_selected"
    INVALID_SHARE_KEYS = "invalid_share_keys"
    INVALID_RECIPIENT_KEY = "invalid_recipient_key"
    PAIRING_CAPACITY = "pairing_capacity"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    CSRF_FAILED = "csrf_failed"
    INVALID_RESET_LINK = "invalid_reset_link"
    INVALID_RECOVERY_CODE = "invalid_recovery_code"
    INVALID_POLICY = "invalid_policy"
    PIN_REQUIRED = "pin_required"
    INVALID_PIN = "invalid_pin"
    LINK_UNAVAILABLE = "link_unavailable"
    HANDLE_TAKEN = "handle_taken"
    INVALID_SEALED_DATA = "invalid_sealed_data"
    CANNOT_CHANGE_OWN_ROLE = "cannot_change_own_role"
    EMAIL_DOMAIN_UNDELIVERABLE = "email_domain_undeliverable"


MESSAGES = {
    ErrorCode.AUTH_REQUIRED: "Entre na sua conta para continuar.",
    ErrorCode.FORBIDDEN: "Acesso não permitido.",
    ErrorCode.NOT_FOUND: "Recurso não encontrado.",
    ErrorCode.INVALID_CREDENTIALS: "Usuário, senha ou código inválido ou já utilizado.",
    ErrorCode.INVALID_VAULT_PASSWORD: "Confira a senha ou entre novamente.",
    ErrorCode.RATE_LIMITED: "Muitas tentativas. Aguarde alguns minutos.",
    ErrorCode.VALIDATION_FAILED: "Confira os campos destacados.",
    ErrorCode.INVALID_INVITE: "Convite inválido, utilizado ou expirado.",
    ErrorCode.USERNAME_TAKEN: "Já existe uma conta com este email.",
    ErrorCode.ENROLLMENT_EXPIRED: "O cadastro expirou. Comece novamente.",
    ErrorCode.INVALID_OTP: "Código inválido.",
    ErrorCode.ENROLLMENT_UNAVAILABLE: "O convite ou o nome de usuário deixou de estar disponível.",
    ErrorCode.STORE_FAILED: "Não foi possível gravar o laudo. Tente novamente.",
    ErrorCode.INVALID_PAIRING_CODE: "Confira o código completo exibido no computador.",
    ErrorCode.PAIRING_UNAVAILABLE: "A solicitação expirou ou já foi usada. Gere outro código no computador.",
    ErrorCode.PAIRING_MISMATCH: "O código não corresponde à chave do computador.",
    ErrorCode.NO_EXAMS_SELECTED: "Selecione pelo menos um documento disponível.",
    ErrorCode.INVALID_SHARE_KEYS: "O navegador não preparou as chaves desta consulta.",
    ErrorCode.INVALID_RECIPIENT_KEY: "Não foi possível iniciar a leitura protegida. Tente em um navegador atualizado.",
    ErrorCode.PAIRING_CAPACITY: "Muitas solicitações. Tente novamente em alguns minutos.",
    ErrorCode.PAYLOAD_TOO_LARGE: "O arquivo excede o tamanho máximo permitido.",
    ErrorCode.CSRF_FAILED: "A sessão do navegador expirou. Atualize a página.",
    ErrorCode.INVALID_RESET_LINK: "Este link é inválido ou expirou. Solicite outro.",
    ErrorCode.INVALID_RECOVERY_CODE: "Código de recuperação ou código do autenticador inválido.",
    ErrorCode.INVALID_POLICY: "Escolha uma duração e um limite de aberturas válidos.",
    ErrorCode.PIN_REQUIRED: "Defina um PIN para links de vários documentos ou com mais de 24 horas.",
    ErrorCode.INVALID_PIN: "PIN incorreto.",
    ErrorCode.LINK_UNAVAILABLE: "Este link expirou, foi encerrado ou já foi aberto.",
    ErrorCode.HANDLE_TAKEN: "Este endereço já está em uso. Escolha outro.",
    ErrorCode.INVALID_SEALED_DATA: "O navegador não preparou os dados cifrados.",
    ErrorCode.CANNOT_CHANGE_OWN_ROLE: "Você não pode alterar o seu próprio acesso de administrador.",
    ErrorCode.EMAIL_DOMAIN_UNDELIVERABLE: "Este domínio não recebe e-mails. Confira o endereço.",
}


def ok(data=None, status: int = 200) -> HttpResponse:
    """Success envelope. 204 responses carry no body."""
    if status == 204:
        return HttpResponse(status=204)
    return JsonResponse({"data": data, "error": None}, status=status)


def fail(code: ErrorCode, status: int, fields: dict | None = None) -> JsonResponse:
    """Error envelope with a stable code and a safe, user-facing message."""
    error = {"code": code.value, "message": MESSAGES[code]}
    if fields:
        error["fields"] = fields
    return JsonResponse({"data": None, "error": error}, status=status)


def form_errors(form) -> dict:
    """Flatten Django form errors into ``{field: first message}``."""
    return {field: errors[0] for field, errors in form.errors.items()}


def csrf_failure(request, reason=""):
    """CSRF_FAILURE_VIEW: same envelope as every other API error."""
    return fail(ErrorCode.CSRF_FAILED, 403)


def not_found(request, exception=None):
    """handler404: API callers get the JSON envelope instead of an HTML page."""
    return fail(ErrorCode.NOT_FOUND, 404)
