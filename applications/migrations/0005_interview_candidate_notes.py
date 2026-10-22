from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0004_jobapplication_match_assessment"),
    ]

    operations = [
        migrations.AddField(
            model_name="interview",
            name="candidate_notes",
            field=models.TextField(blank=True),
        ),
    ]
