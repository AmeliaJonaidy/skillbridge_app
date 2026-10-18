from django.contrib import admin

from .models import Company, RecruiterProfile


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "verification_status")
    search_fields = ("name", "industry")


@admin.register(RecruiterProfile)
class RecruiterProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "job_title")
    search_fields = ("user__username", "company__name")
