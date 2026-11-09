import accounts.models
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def populate_referral_codes(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    for profile in UserProfile.objects.filter(referral_code__isnull=True):
        profile.referral_code = uuid.uuid4().hex[:10].upper()
        profile.save(update_fields=["referral_code"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_alter_payment_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="referral_code",
            field=models.CharField(max_length=10, null=True),
        ),
        migrations.RunPython(populate_referral_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userprofile",
            name="referral_code",
            field=models.CharField(default=accounts.models.generate_referral_code, max_length=10, unique=True),
        ),
        migrations.CreateModel(
            name="Referral",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("referral_code", models.CharField(max_length=10)),
                ("reward_days", models.PositiveSmallIntegerField(default=7)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("rewarded", "Rewarded"), ("partial", "Partially rewarded"), ("failed", "Failed")], default="pending", max_length=20)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("rewarded_at", models.DateTimeField(blank=True, null=True)),
                ("referred_user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="referral_received", to=settings.AUTH_USER_MODEL)),
                ("referrer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="referrals_made", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
