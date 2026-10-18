from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_userprofile_profile_data_userprofile_resume_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="userprofile",
            name="resume",
        ),
    ]
