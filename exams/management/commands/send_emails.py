import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from exams.outbox import process_due


class Command(BaseCommand):
    help = "Envia os emails da fila (convites, redefinição de senha). Rode continuamente ou com --once."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="processa a fila uma vez e sai")

    def handle(self, *args, **options):
        mode = "SMTP" if settings.EMAIL_ENABLED else "console (EMAIL_ENABLED=false)"
        self.stdout.write(f"Email worker started: {mode}")
        while True:
            close_old_connections()
            process_due()
            if options["once"]:
                return
            time.sleep(settings.EMAIL_WORKER_INTERVAL_SECONDS)
