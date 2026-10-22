from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_remove_userprofile_resume"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="resume",
            field=models.FileField(blank=True, null=True, upload_to="resumes/"),
        ),
    ]
