from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from accounts.models import UserProfile
from employers.models import Company
from jobs.models import Job
from resumes.services import build_tailored_cover_letter, build_tailored_resume

from .forms import CandidateProfileForm
from .models import CandidateMilestone, CandidateProfile, Certification
from .career_paths import career_progress


class ResumeAutofillTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.user = User.objects.create_user(username="autofill", password="Password123!")
        UserProfile.objects.create(user=self.user, role="candidate")
        self.client.force_login(self.user)

    def test_text_resume_autofills_blank_profile_fields(self):
        resume = SimpleUploadedFile(
            "resume.txt",
            b"Skills\nPython, Django, SQL\nExperience\nBackend intern at a fintech company\nLinkedIn https://linkedin.com/in/autofill",
            content_type="text/plain",
        )

        response = self.client.post(
            "/profile/",
            {"action": "autofill", "resume": resume},
        )

        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.user)
        self.assertIn("Python", profile.profile_data["skills"])
        self.assertEqual(profile.profile_data["career"], "technology")
        self.assertEqual(profile.profile_data["linkedin"], "https://linkedin.com/in/autofill")

    def test_resume_page_shows_feedback_for_uploaded_resume(self):
        resume = SimpleUploadedFile(
            "review.txt",
            b"Skills\nPython, Django\nExperience\nBackend intern with 20% faster API response\n",
            content_type="text/plain",
        )
        self.client.post("/profile/", {"action": "autofill", "resume": resume})

        response = self.client.get("/resume/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resume feedback")
        self.assertContains(response, "Detected skills")

    def test_pro_learning_recommends_certification_for_missing_job_skill(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.plan = "pro"
        profile.profile_data = {
            "name": "Alex Candidate",
            "career": "technology",
            "specialisation": "backend",
            "skills": "Python, Django",
        }
        profile.save(update_fields=["plan", "profile_data"])
        recruiter = User.objects.create_user(username="learning_recruiter", password="Password123!")
        company = Company.objects.create(name="Learning Company")
        job = Job.objects.create(
            company=company,
            created_by=recruiter,
            title="Cloud Backend Engineer",
            description="Build cloud services.",
            industry="technology",
            employment_type="full_time",
            required_skills="Python, AWS",
        )
        Certification.objects.create(
            title="AWS Cloud Foundations",
            provider="AWS",
            career_area="technology",
            skills="AWS, Cloud infrastructure",
            url="https://example.com/aws",
        )

        response = self.client.get(reverse("candidate_learning"), {"job": job.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cloud Backend Engineer")
        self.assertContains(response, "AWS Cloud Foundations")
        self.assertContains(response, "AWS")


class CareerProgressTests(TestCase):
    def test_completed_certificate_is_visible_in_profile_resume_and_tailored_resume(self):
        user = User.objects.create_user(username="certificate-sync", password="testpass123")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"name": "Certificate Candidate"},
        )
        certification = Certification.objects.create(
            title="Google Data Analytics",
            provider="Google",
            career_area="technology",
        )
        CandidateMilestone.objects.create(
            candidate=user,
            certification=certification,
            status="completed",
            certificate_id="GDA-123",
            completed_at=timezone.now(),
        )
        recruiter = User.objects.create_user(username="certificate-recruiter", password="testpass123")
        company = Company.objects.create(name="Certificate Company")
        job = Job.objects.create(
            company=company,
            created_by=recruiter,
            title="Data Analyst",
            description="Analyse business data.",
            employment_type="full_time",
        )
        self.client.force_login(user)

        profile_response = self.client.get(reverse("candidate_profile"))
        resume_response = self.client.get(reverse("candidate_resume"))
        tailored_resume = build_tailored_resume(user, job)

        self.assertContains(profile_response, "Google Data Analytics (Certificate ID: GDA-123)")
        self.assertContains(resume_response, "Google Data Analytics (Certificate ID: GDA-123)")
        self.assertIn("Google Data Analytics (Certificate ID: GDA-123)", tailored_resume)
        self.assertEqual(
            CandidateProfile.objects.get(user=user).certifications,
            "Google Data Analytics (Certificate ID: GDA-123)",
        )
    def test_linkedin_profile_accepts_url_without_scheme(self):
        form = CandidateProfileForm(data={"linkedin": "linkedin.com/in/jamie"})

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["linkedin"], "https://linkedin.com/in/jamie")

    def test_profile_combines_country_code_and_phone_number(self):
        user = User.objects.create_user(username="phone", password="Password123!")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)

        response = self.client.post(
            "/profile/",
            {"phone_country_code": "+65", "phone": "81234567"},
        )

        self.assertRedirects(response, reverse("candidate_profile"))
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.profile_data["phone_country_code"], "+65")
        self.assertEqual(profile.profile_data["phone"], "+65 81234567")

        response = self.client.get("/profile/")
        self.assertContains(response, 'value="81234567"')

    def test_saved_profile_data_is_used_by_resume_page(self):
        user = User.objects.create_user(username="profile-resume-sync", password="testpass123")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)

        response = self.client.post(
            reverse("candidate_profile"),
            {
                "name": "Jamie Updated",
                "career": "business",
                "specialisation": "business-analysis",
                "career_stage": "beginner",
                "career_interests": ["business-analysis"],
                "education": "undergraduate",
                "institution": "nus",
                "experience": "Analysed customer data for a market research project.",
                "certifications": "Google Data Analytics",
                "skills": "Excel, SQL",
                "portfolio": "https://example.com/project",
                "awards": "Dean's list",
                "linkedin": "linkedin.com/in/jamie-updated",
                "visa": "citizen",
                "phone_country_code": "+65",
                "phone": "81234567",
                "email": "jamie@example.com",
            },
        )

        self.assertRedirects(response, reverse("candidate_profile"))
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.profile_data["name"], "Jamie Updated")
        self.assertEqual(profile.profile_data["skills"], "Excel, SQL")
        resume_response = self.client.get(reverse("candidate_resume"))
        self.assertContains(resume_response, "Jamie Updated")
        self.assertContains(resume_response, "Google Data Analytics")
        self.assertContains(resume_response, "Excel, SQL")
        self.assertContains(resume_response, "Business")
        self.assertContains(resume_response, "Business analysis")
        self.assertContains(resume_response, "National University of Singapore (NUS)")

    def test_saved_career_directions_are_used_by_skill_development(self):
        user = User.objects.create_user(username="direction-save", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"career_interests": ["machine-learning"], "specialisation": "ai-ml"},
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("candidate_profile"),
            {
                "career_interests": ["software-engineering", "fintech"],
                "phone_country_code": "+65",
                "phone": "81234567",
            },
        )

        self.assertRedirects(response, reverse("candidate_profile"))
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.profile_data["career_interests"], ["software-engineering", "fintech"])

        response = self.client.get(reverse("candidate_learning"))

        self.assertContains(response, "Fintech")
        self.assertNotContains(response, "Machine learning")
        self.assertNotContains(response, "ai-ml")
        self.assertNotContains(response, "Microbiology")

    def test_progress_only_contains_selected_career_directions(self):
        user = User.objects.create_user(username="progress", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "career_interests": ["software-engineering", "machine-learning"],
                "skills": "Python, Django",
            },
        )

        progress = career_progress(user, ["software-engineering", "machine-learning"])

        self.assertEqual([item["key"] for item in progress], ["software-engineering", "machine-learning"])
        self.assertEqual(progress[0]["percent"], 40)
        self.assertEqual(progress[1]["percent"], 20)
        self.assertTrue(progress[0]["recommendations"])
        self.assertTrue(progress[0]["missing"])
        self.assertTrue(progress[0]["milestones"])
        self.assertEqual(progress[0]["milestones"][0]["skill"], "Git")
        self.assertTrue(progress[0]["milestones"][0]["courses"])

    def test_interdisciplinary_path_has_ordered_activity_and_evidence_stages(self):
        user = User.objects.create_user(username="bioinformatics", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "career_interests": ["bioinformatics"],
                "career_stage": "beginner",
                "skills": "Python",
            },
        )

        goal = career_progress(user, ["bioinformatics"])[0]

        self.assertEqual(goal["label"], "Bioinformatics / computational biology")
        self.assertEqual(goal["current_stage_label"], "Beginner")
        self.assertEqual(len(goal["milestones"]), 3)
        self.assertTrue(goal["milestones"][0]["activity"])
        self.assertTrue(goal["milestones"][0]["evidence"])
        self.assertTrue(goal["recommendations"])

    def test_learning_roadmap_uses_specialisation_when_directions_are_legacy(self):
        user = User.objects.create_user(username="legacy-direction", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"specialisation": "backend", "skills": "Python"},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("candidate_learning"))

        self.assertContains(response, "Software engineering")
        self.assertContains(response, "ROADMAP FROM YOUR CURRENT EVIDENCE")
        self.assertContains(response, "Google IT Automation with Python Professional Certificate")

    def test_uploaded_resume_evidence_changes_the_target_roadmap(self):
        with TemporaryDirectory() as media_directory:
            with override_settings(MEDIA_ROOT=media_directory):
                user = User.objects.create_user(username="resume-roadmap", password="Password123!")
                profile = UserProfile.objects.create(
                    user=user,
                    role="candidate",
                    profile_data={"career_interests": ["software-engineering"]},
                )
                profile.resume.save(
                    "resume.txt",
                    SimpleUploadedFile(
                        "resume.txt",
                        b"Skills\nPython, Git\nExperience\nBuilt APIs with Django and SQL.",
                        content_type="text/plain",
                    ),
                    save=True,
                )

                progress = career_progress(user, ["software-engineering"])[0]

        self.assertIn("Python", progress["matched"])
        self.assertIn("Git", progress["matched"])
        self.assertNotIn("Python", progress["missing"])

    def test_unselected_direction_is_not_added_to_progress(self):
        user = User.objects.create_user(username="selected-only", password="Password123!")
        UserProfile.objects.create(user=user, role="candidate", profile_data={"skills": "Python"})

        progress = career_progress(user, ["marketing"])

        self.assertEqual(len(progress), 1)
        self.assertEqual(progress[0]["label"], "Marketing")

    def test_completing_catalogue_course_updates_readiness_evidence(self):
        user = User.objects.create_user(username="course-complete", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "career_interests": ["software-engineering"],
                "skills": "Python, Django",
            },
        )
        self.client.force_login(user)

        with TemporaryDirectory() as media_directory:
            with override_settings(MEDIA_ROOT=media_directory):
                response = self.client.post(
                    "/learning/",
                    {
                        "action": "complete_course",
                        "career_key": "software-engineering",
                        "course_title": "Google IT Automation with Python Professional Certificate",
                        "evidence_file": SimpleUploadedFile(
                            "python-certificate.pdf",
                            b"%PDF-1.4 certificate evidence",
                            content_type="application/pdf",
                        ),
                    },
                )

        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=user)
        self.assertIn(
            "Google IT Automation with Python Professional Certificate",
            profile.profile_data["completed_career_courses"],
        )
        milestone = CandidateMilestone.objects.get(candidate=user)
        self.assertEqual(milestone.status, "completed")
        self.assertTrue(milestone.evidence_file)
        self.assertEqual(career_progress(user, ["software-engineering"])[0]["percent"], 80)

    def test_course_cannot_be_marked_completed_without_uploaded_evidence(self):
        user = User.objects.create_user(username="course-proof", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={"career_interests": ["software-engineering"]},
        )
        self.client.force_login(user)

        response = self.client.post(
            "/learning/",
            {
                "action": "complete_course",
                "career_key": "software-engineering",
                "course_title": "Google IT Automation with Python Professional Certificate",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CandidateMilestone.objects.filter(candidate=user).exists())

    def test_cover_letter_prioritises_business_evidence_for_business_role(self):
        user = User.objects.create_user(username="letter", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "name": "Jamie Candidate",
                "career": "business",
                "specialisation": "business-analysis",
                "skills": "Excel, SQL",
                "portfolio": "Built a marketing dashboard that helped a retail business compare campaign performance.",
            },
        )
        recruiter = User.objects.create_user(username="letter-recruiter", password="Password123!")
        company = Company.objects.create(name="Business Company")
        job = Job.objects.create(
            company=company,
            created_by=recruiter,
            title="Business Analyst Intern",
            description="Gather stakeholder requirements and support market analysis.",
            industry="consulting",
            employment_type="internship",
            required_skills="Excel, SQL",
        )

        letter = build_tailored_cover_letter(user, job)

        self.assertIn("Business Analyst Intern", letter)
        self.assertIn("business-facing projects and experience", letter)
        self.assertIn("marketing dashboard", letter)

        tailored_resume = build_tailored_resume(user, job)
        self.assertIn("marketing dashboard", tailored_resume)
        self.assertNotIn("EMPLOYER DETAILS USED", tailored_resume)
        self.assertNotIn("JOB DESCRIPTION PRIORITIES", tailored_resume)
        self.assertNotIn("TAILORING NOTES", tailored_resume)

    def test_tailored_resume_contextualises_generic_coding_statement(self):
        user = User.objects.create_user(username="data-candidate", password="test-pass")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "name": "Data Candidate",
                "career": "computer science",
                "experience": "I like to code",
            },
        )
        recruiter = User.objects.create_user(username="data-recruiter", password="test-pass")
        company = Company.objects.create(name="Data Company")
        job = Job.objects.create(
            company=company,
            created_by=recruiter,
            title="Data Analyst",
            description="Analyse and visualise data for business decisions.",
            employment_type="full_time",
            required_skills="SQL, Excel",
        )

        tailored_resume = build_tailored_resume(user, job)

        self.assertIn("I enjoy using code to analyse and visualise data.", tailored_resume)
        self.assertNotIn("I like to code", tailored_resume)

    def test_dashboard_links_selected_directions_to_progress_page(self):
        user = User.objects.create_user(username="dashboard-progress", password="Password123!")
        UserProfile.objects.create(
            user=user,
            role="candidate",
            profile_data={
                "career_interests": ["marketing"],
                "skills": "marketing, SEO",
            },
        )
        self.client.force_login(user)
        session = self.client.session
        session["onboarding_complete"] = True
        session.save()

        response = self.client.get("/")

        self.assertContains(response, "Career readiness")
        self.assertContains(response, "40%")
        self.assertContains(response, "View Marketing roadmap")
        self.assertContains(response, "View progress and certifications")

# Create your tests here.
