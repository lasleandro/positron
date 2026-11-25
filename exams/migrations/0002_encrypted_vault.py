import django.db.models.deletion
from django.db import migrations, models


def require_empty_previous_installation(apps, schema_editor):
    alias = schema_editor.connection.alias
    for app, model in (("auth", "User"), ("exams", "Exam"), ("exams", "Consultation")):
        if apps.get_model(app, model).objects.using(alias).exists():
            raise RuntimeError(
                "A versão anterior tem dados. Preserve o banco e implante o cofre em um banco novo. "
                "Recrie as contas e reenvie os PDFs originais pelo navegador."
            )


class Migration(migrations.Migration):
    dependencies = [("exams", "0001_initial")]

    operations = [
        migrations.RunPython(require_empty_previous_installation),
        migrations.RenameField("exam", "pdf", "ciphertext"),
        migrations.AddField("exam", "wrapped_key", models.CharField(max_length=82, default=""), preserve_default=False),
        migrations.AddField("consultation", "recipient_key", models.CharField(max_length=87, default=""), preserve_default=False),
        migrations.AddField("consultation", "sender_key", models.CharField(max_length=87, blank=True)),
        migrations.RemoveField("consultation", "exams"),
        migrations.CreateModel(
            name="SharedExam",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("wrapped_key", models.CharField(max_length=82)),
                ("consultation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="exams.consultation")),
                ("exam", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="exams.exam")),
            ],
            options={"constraints": [
                models.UniqueConstraint(fields=("consultation", "exam"), name="unique_consultation_exam"),
            ]},
        ),
        migrations.AddField(
            "consultation", "exams",
            models.ManyToManyField(related_name="consultations", through="exams.SharedExam", to="exams.exam"),
        ),
    ]
