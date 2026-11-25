from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from exams.models import EmailDelivery, Grant, Invitation, PasswordResetToken


class Command(BaseCommand):
    help = "Invalida sessões, consultas e convites em uma restauração do banco."

    def add_arguments(self, parser):
        parser.add_argument("--confirm-restore", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_restore"]:
            raise CommandError("Use --confirm-restore após parar o tráfego na instância restaurada.")
        with transaction.atomic():
            Session.objects.all().delete()
            Grant.objects.all().delete()
            Invitation.objects.all().delete()
            PasswordResetToken.objects.all().delete()
            EmailDelivery.objects.exclude(status__in=("sent", "failed", "suppressed")).delete()
        self.stdout.write("Sessões, consultas, convites e links de redefinição invalidados.")
