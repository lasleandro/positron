import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def drop_unbound_invitations(apps, schema_editor):
    """Pre-email invitations cannot be bound to an address, so they stop being valid."""
    apps.get_model("exams", "Invitation").objects.using(schema_editor.connection.alias).all().delete()


def require_no_accounts(apps, schema_editor):
    """Accounts created before the vault split have no wrapped vault key and cannot log in."""
    if apps.get_model("auth", "User").objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError(
            "Contas anteriores ao cofre com código de recuperação não são compatíveis. "
            "Use um banco novo e recrie as contas por convite."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0002_encrypted_vault"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(require_no_accounts, migrations.RunPython.noop),
        migrations.RunPython(drop_unbound_invitations, migrations.RunPython.noop),
        migrations.AddField(
            "invitation", "email",
            models.EmailField(db_index=True, max_length=150, default=""), preserve_default=False,
        ),
        migrations.AddField("invitation", "grants_staff", models.BooleanField(default=False)),
        migrations.CreateModel(
            name="AccountVault",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("wrapped_password", models.CharField(max_length=82)),
                ("wrapped_recovery", models.CharField(max_length=82)),
                ("recovery_verifier", models.CharField(max_length=128)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="PasswordResetToken",
            fields=[
                ("digest", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("consumed_at", models.DateTimeField(null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="EmailDelivery",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("purpose", models.CharField(choices=[("invitation", "invitation"), ("password_reset", "password_reset"), ("password_changed", "password_changed")], max_length=32)),
                ("to_address", models.EmailField(max_length=150)),
                ("grants_staff", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("queued", "queued"), ("processing", "processing"), ("retry_wait", "retry_wait"), ("sent", "sent"), ("failed", "failed"), ("suppressed", "suppressed")], db_index=True, default="queued", max_length=16)),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(null=True)),
                ("last_error_code", models.CharField(blank=True, max_length=40)),
                ("sent_at", models.DateTimeField(null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
