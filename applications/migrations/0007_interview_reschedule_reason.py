from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0006_interview_reschedule_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="interview",
            name="reschedule_reason",
            field=models.TextField(blank=True),
        ),
    ]
