from django.contrib import admin

from .models import TailoredResume


@admin.register(TailoredResume)
class TailoredResumeAdmin(admin.ModelAdmin):
    list_display = ("candidate", "job", "title", "updated_at")
    search_fields = ("candidate__username", "job__title")
