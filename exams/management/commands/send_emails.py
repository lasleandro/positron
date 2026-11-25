import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from exams.bounces import bounce_checks_enabled, check_bounces
from exams.outbox import process_due

logger = logging.getLogger("exams.outbox")


def run_bounce_check() -> None:
    """Never lets a mailbox problem stop the outbox: failures are logged and retried next round."""
    try:
        check_bounces()
    except Exception:
        logger.exception("bounce check failed")


class Command(BaseCommand):
    help = "Envia os emails da fila (convites, redefinição de senha) e lê os avisos de não entrega."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="processa a fila uma vez e sai")

    def handle(self, *args, **options):
        mode = "SMTP" if settings.EMAIL_ENABLED else "console (EMAIL_ENABLED=false)"
        bounces = "on" if bounce_checks_enabled() else "off"
        self.stdout.write(f"Email worker started: {mode}, bounce checks {bounces}")
        next_bounce_check = 0.0
        while True:
            close_old_connections()
            process_due()
            if bounce_checks_enabled() and time.monotonic() >= next_bounce_check:
                run_bounce_check()
                next_bounce_check = time.monotonic() + settings.EMAIL_BOUNCE_CHECK_SECONDS
            if options["once"]:
                return
            time.sleep(settings.EMAIL_WORKER_INTERVAL_SECONDS)
