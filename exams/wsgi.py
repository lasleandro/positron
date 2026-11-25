import os

from django.conf import settings
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "exams.settings")
application = get_wsgi_application()

if not settings.DEBUG:
    from .security import mfa_cipher

    mfa_cipher()
