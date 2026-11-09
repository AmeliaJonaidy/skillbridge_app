from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("candidates", "0004_candidatemilestone_certificate_id")]

    operations = [
        migrations.AlterField(
            model_name="candidatemilestone",
            name="status",
            field=models.CharField(
                choices=[
                    ("planned", "Planned"),
                    ("in_progress", "In progress"),
                    ("pending_verification", "Pending verification"),
                    ("completed", "Completed"),
                ],
                default="planned",
                max_length=20,
            ),
        ),
    ]
