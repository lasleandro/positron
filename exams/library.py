"""Owner library: list, upload and fetch encrypted documents.

Titles and issuers are sealed in the browser, so the server cannot search them; the SPA loads
the pages and filters after decrypting locally.
"""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from .forms import UploadForm
from .models import Document, Grant
from .policy import end_grant, record_event
from .responses import ErrorCode, fail, form_errors, ok
from .security import audit, owner_required

LIST_FIELDS = ("id", "sealed_title", "sealed_issuer", "document_date", "wrapped_key")
SUMMARY_FIELDS = ("id", "sealed_title", "sealed_issuer", "document_date")


def document_summary(document: Document) -> dict:
    return {
        "id": str(document.id),
        "sealed_title": document.sealed_title,
        "sealed_issuer": document.sealed_issuer,
        "document_date": document.document_date.isoformat(),
    }


def owner_document(document: Document) -> dict:
    """The owner's view also carries the vault-wrapped data key (needed to share or open)."""
    return {**document_summary(document), "wrapped_key": document.wrapped_key}


def encrypted_response(ciphertext, wrapped_key) -> HttpResponse:
    response = HttpResponse(bytes(ciphertext), content_type="application/octet-stream")
    response["X-Document-Key"] = wrapped_key
    response["Content-Disposition"] = 'attachment; filename="documento.enc"'
    return response


def page_number(request) -> int:
    try:
        return max(1, int(request.GET.get("page", 1)))
    except ValueError:
        return 1


def list_documents(request):
    page = page_number(request)
    size = settings.EXAM_PAGE_SIZE
    documents = Document.objects.filter(owner=request.user).only(*LIST_FIELDS)
    window = list(documents[(page - 1) * size: page * size + 1])
    return ok({
        "items": [owner_document(document) for document in window[:size]],
        "next_page": page + 1 if len(window) > size else None,
    })


def create_document(request):
    form = UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return fail(ErrorCode.VALIDATION_FAILED, 400, form_errors(form))
    data = form.cleaned_data.copy()
    data["ciphertext"] = data["ciphertext"].read()
    try:
        document = Document.objects.create(owner=request.user, **data)
    except IntegrityError:
        return fail(ErrorCode.STORE_FAILED, 409)
    audit(request, "document.uploaded", document=document.id)
    return ok(owner_document(document), status=201)


@require_http_methods(["GET", "POST"])
@owner_required
def documents(request):
    return create_document(request) if request.method == "POST" else list_documents(request)


def delete_document(request, document_id):
    """Delete the ciphertext for good. Grants left without documents end (nothing left to read)."""
    with transaction.atomic():
        document = Document.objects.filter(pk=document_id, owner=request.user).first()
        if document is None:
            return ok(status=204)
        affected = list(Grant.objects.filter(owner=request.user, documents=document, ended_at__isnull=True))
        document.delete()
        emptied = [grant for grant in affected if not grant.grantdocument_set.exists()]
        for grant in emptied:
            end_grant(grant, "revoked")
    for grant in emptied:
        record_event(grant, "ended", detail="documento excluído")
    audit(request, "document.deleted", document=document_id)
    return ok(status=204)


@require_http_methods(["GET", "DELETE"])
@owner_required
def document_detail(request, document_id):
    if request.method == "DELETE":
        return delete_document(request, document_id)
    document = get_object_or_404(Document.objects.only(*LIST_FIELDS), pk=document_id, owner=request.user)
    return ok(owner_document(document))


@require_GET
@owner_required
def document_content(request, document_id):
    document = get_object_or_404(
        Document.objects.only("ciphertext", "wrapped_key"), pk=document_id, owner=request.user,
    )
    return encrypted_response(document.ciphertext, document.wrapped_key)
