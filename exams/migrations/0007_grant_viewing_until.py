from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0006_consent_records"),
    ]

    operations = [
        migrations.AddField(
            model_name="grant",
            name="viewing_until",
            field=models.DateTimeField(null=True),
        ),
    ]
