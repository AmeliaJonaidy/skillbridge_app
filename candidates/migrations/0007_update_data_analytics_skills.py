from django.db import migrations


def add_sql_to_data_analytics_certificate(apps, schema_editor):
    Certification = apps.get_model("candidates", "Certification")
    Certification.objects.filter(
        title="Google Advanced Data Analytics Professional Certificate",
        provider="Coursera",
    ).update(skills="Python, SQL, statistics, machine learning, analytics")


class Migration(migrations.Migration):
    dependencies = [
        ("candidates", "0006_candidatemilestone_verification_fields"),
    ]

    operations = [
        migrations.RunPython(
            add_sql_to_data_analytics_certificate,
            migrations.RunPython.noop,
        ),
    ]
