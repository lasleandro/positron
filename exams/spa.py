"""Serve the React build's index.html for every client-side route."""

from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def index(request, path=""):
    page = settings.FRONTEND_DIST / "index.html"
    if not page.is_file():
        return HttpResponse(
            "Frontend não compilado. Use python start_server.py (dev) ou npm run build em frontend/.",
            status=503, content_type="text/plain; charset=utf-8",
        )
    return FileResponse(page.open("rb"), content_type="text/html; charset=utf-8")
