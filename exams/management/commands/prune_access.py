import time
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from exams.models import EmailDelivery, Grant, Invitation, PasswordResetToken, SecurityState


class Command(BaseCommand):
    help = "Remove permissões, convites e sessões expirados há mais de um dia (o histórico é mantido)."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=1)
        Grant.objects.filter(
            Q(expires_at__lt=cutoff)
            | Q(expires_at__isnull=True, pair_until__lt=cutoff)
            | Q(ended_at__lt=cutoff),
        ).delete()
        Invitation.objects.filter(expires_at__lt=cutoff).delete()
        PasswordResetToken.objects.filter(expires_at__lt=cutoff).delete()
        EmailDelivery.objects.filter(status__in=("sent", "failed", "suppressed"), updated_at__lt=cutoff).delete()
        SecurityState.objects.filter(bucket__lt=int(time.time()) // 300 - 288).exclude(name="bootstrap").delete()
        call_command("clearsessions")
