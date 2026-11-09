from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("candidates", "0005_alter_candidatemilestone_status")]

    operations = [
        migrations.AddField(model_name="candidatemilestone", name="verification_url", field=models.URLField(blank=True, max_length=500)),
        migrations.AddField(model_name="candidatemilestone", name="verification_method", field=models.CharField(blank=True, max_length=50)),
        migrations.AddField(model_name="candidatemilestone", name="verification_details", field=models.TextField(blank=True)),
        migrations.AddField(model_name="candidatemilestone", name="verified_at", field=models.DateTimeField(blank=True, null=True)),
    ]
