from django.test import TestCase

# Create your tests here.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from employers.models import Company, RecruiterProfile
from jobs.models import Job

from .models import Interview, JobApplication


class ApplicationWorkflowTests(TestCase):
    def setUp(self):
        self.candidate = User.objects.create_user(
            username="candidate",
            email="candidate@example.com",
            password="TestPassword123!",
        )
        UserProfile.objects.create(
            user=self.candidate,
            role="candidate",
            profile_data={"skills": "Python, Django"},
        )
        self.recruiter = User.objects.create_user(
            username="recruiter",
            email="recruiter@example.com",
            password="TestPassword123!",
        )
        UserProfile.objects.create(user=self.recruiter, role="recruiter")
        self.company = Company.objects.create(name="Test Company")
        RecruiterProfile.objects.create(user=self.recruiter, company=self.company)
        self.job = Job.objects.create(
            company=self.company,
            created_by=self.recruiter,
            title="Backend intern",
            description="Build Django services.",
            employment_type="internship",
            required_skills="Python, Django, JavaScript",
        )

    def test_candidate_can_apply_and_receives_match_score(self):
        self.client.force_login(self.candidate)
        response = self.client.post(
            reverse("job_detail", args=[self.job.pk]),
            {"action": "apply", "cover_note": "I am interested."},
        )

        self.assertRedirects(response, reverse("candidate_applications"))
        application = JobApplication.objects.get(candidate=self.candidate, job=self.job)
        self.assertEqual(application.match_score, 67)
        self.assertEqual(application.missing_skills, ["JavaScript"])

    def test_recruiter_can_update_status_and_schedule_interview(self):
        JobApplication.objects.create(candidate=self.candidate, job=self.job)
        application = JobApplication.objects.get(candidate=self.candidate, job=self.job)
        self.client.force_login(self.recruiter)

        response = self.client.post(
            reverse("recruiter_applicants"),
            {"application_id": application.pk, "status": "shortlisted"},
        )
        self.assertRedirects(response, reverse("recruiter_applicants"))
        application.refresh_from_db()
        self.assertEqual(application.status, "shortlisted")

        response = self.client.post(
            reverse("recruiter_calendar"),
            {
                "application_id": application.pk,
                "scheduled_start": "2026-10-22T14:00",
                "meeting_url": "https://cal.com/interview",
                "notes": "Technical discussion",
            },
        )
        self.assertRedirects(response, reverse("recruiter_calendar"))
        self.assertEqual(Interview.objects.filter(application=application).count(), 1)
