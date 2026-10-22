from django.contrib import admin

from .models import CandidateMilestone, CandidateProfile, Certification


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "career_area", "specialisation", "profile_complete_percent", "updated_at")
    search_fields = ("user__username", "career_area", "technical_skills")


@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ("title", "provider", "career_area", "cost", "is_recognised")
    list_filter = ("career_area", "is_recognised")
    search_fields = ("title", "provider", "skills")


@admin.register(CandidateMilestone)
class CandidateMilestoneAdmin(admin.ModelAdmin):
    list_display = ("candidate", "certification", "status", "has_evidence", "completed_at")
    list_filter = ("status",)

    @admin.display(boolean=True, description="Evidence")
    def has_evidence(self, milestone):
        return bool(milestone.evidence_file)
