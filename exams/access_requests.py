"""Public "Solicitar acesso": forwards the request to the team inbox (no self-signup yet)."""

from django.conf import settings
from django.views.decorators.http import require_POST

from .forms import AccessRequestForm
from .models import AccessRequest, EmailDelivery
from .outbox import enqueue
from .responses import ErrorCode, fail, form_errors, ok
from .security import allow_attempt, audit, json_body, rate_key

REPLY = {"message": "Recebemos sua solicitação. Vamos responder pelo e-mail informado."}


@require_POST
def create_access_request(request):
    form = AccessRequestForm(json_body(request))
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    data = form.cleaned_data
    if data["website"]:
        return ok(REPLY, status=202)  # bot filled the honeypot: same answer, nothing sent
    ip = request.META.get("REMOTE_ADDR", "")
    if not (allow_attempt("access-request", 30, 300) and allow_attempt(rate_key("acc-req-ip", ip), 10, 3600)
            and allow_attempt(rate_key("acc-req", data["email"]), 3, 3600)):
        return fail(ErrorCode.RATE_LIMITED, 429)
    access_request = AccessRequest.objects.create(
        email=data["email"], name=data["name"].strip(), message=data["message"].strip(),
    )
    enqueue(EmailDelivery.ACCESS_REQUEST, settings.CONTACT_EMAIL, access_request=access_request)
    audit(request, "access_request.created")
    return ok(REPLY, status=202)
