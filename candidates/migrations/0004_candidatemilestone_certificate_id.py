from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("candidates", "0003_candidatemilestone_evidence_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidatemilestone",
            name="certificate_id",
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
