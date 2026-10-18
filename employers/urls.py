from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="recruiter_dashboard"),
    path("jobs/", views.listings, name="recruiter_listings"),
    path("applicants/", views.applicants, name="recruiter_applicants"),
    path("applicants/<int:application_id>/", views.applicant_detail, name="recruiter_applicant_detail"),
    path("calendar/", views.calendar, name="recruiter_calendar"),
    path("company/", views.company, name="recruiter_company"),
]
