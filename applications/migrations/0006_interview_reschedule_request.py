from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0005_interview_candidate_notes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="interview",
            name="proposed_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="interview",
            name="proposed_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="interview",
            name="reschedule_message",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="interview",
            name="reschedule_status",
            field=models.CharField(blank=True, choices=[("", "No pending request"), ("pending", "Pending recruiter review"), ("accepted", "Accepted"), ("rejected", "Rejected")], max_length=20),
        ),
        migrations.AddField(
            model_name="interview",
            name="reschedule_requested_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="interview_reschedule_requests", to=settings.AUTH_USER_MODEL),
        ),
    ]
