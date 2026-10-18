from django.contrib import admin

from .models import JobMatch


@admin.register(JobMatch)
class JobMatchAdmin(admin.ModelAdmin):
    list_display = ("candidate", "job", "score", "created_at")
    list_filter = ("score",)
