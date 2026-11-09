from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("resumes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tailoredresume",
            name="is_main",
            field=models.BooleanField(default=False),
        ),
    ]
