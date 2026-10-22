from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile

from django.urls import reverse

from .forms import SignupForm
from .models import UserProfile


class AccountOnboardingTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.addCleanup(self.media_directory.cleanup)

    def test_login_shows_red_error_for_invalid_credentials(self):
        response = self.client.post(
            reverse("login"),
            {"username": "unknown", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username/email or password.")
        self.assertContains(response, 'class="errorlist nonfield"')

    def test_profile_initials_use_onboarding_name(self):
        user = UserProfile.objects.create(
            user=self._create_user("candidate"),
            role="candidate",
            profile_data={"name": "Alex Tan"},
        )

        self.assertEqual(user.initials, "AT")

    def _create_user(self, username):
        from django.contrib.auth.models import User

        return User.objects.create_user(username=username, password="password")

    def test_signup_does_not_collect_name(self):
        self.assertNotIn("first_name", SignupForm.base_fields)
        self.assertNotIn("last_name", SignupForm.base_fields)

    def test_candidate_onboarding_starts_with_resume_upload(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "candidate",
                "email": "candidate@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "candidate",
            },
        )

        self.assertRedirects(response, reverse("onboarding"))
        response = self.client.get(reverse("onboarding"))

        self.assertContains(response, "Upload your current resume")
        self.assertContains(response, 'type="file"')
        self.assertContains(response, "multipart/form-data")
        self.assertContains(response, "Skip for now")

    def test_candidate_name_is_saved_from_onboarding(self):
        user = self.client.post(
            reverse("signup"),
            {
                "username": "candidate",
                "email": "candidate@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "candidate",
            },
        )
        self.assertEqual(user.status_code, 302)

        response = self.client.post(
            reverse("onboarding"),
            {"resume": SimpleUploadedFile("alex-resume.pdf", b"resume contents", content_type="application/pdf")},
        )

        self.assertRedirects(response, reverse("onboarding"))
        resume_name = UserProfile.objects.get(user__username="candidate").resume.name
        self.assertIn("alex-resume", resume_name)
        self.assertTrue(resume_name.endswith(".pdf"))

        response = self.client.post(reverse("onboarding"), {"name": "Alex Tan"})
        self.assertRedirects(response, reverse("onboarding"))
        self.assertEqual(
            UserProfile.objects.get(user__username="candidate").profile_data["name"],
            "Alex Tan",
        )

    def test_candidate_can_replace_resume_from_profile(self):
        from django.contrib.auth.models import User

        user = self._create_user("profile_candidate")
        UserProfile.objects.create(user=user, role="candidate", profile_data={"name": "Alex Tan"})
        self.client.force_login(user)

        response = self.client.post(
            reverse("candidate_profile"),
            {"resume": SimpleUploadedFile("updated-resume.pdf", b"updated", content_type="application/pdf")},
        )

        self.assertEqual(response.status_code, 200)
        resume_name = UserProfile.objects.get(user=user).resume.name
        self.assertIn("updated-resume", resume_name)
        self.assertTrue(resume_name.endswith(".pdf"))

    def test_existing_account_login_goes_to_dashboard(self):
        from django.contrib.auth.models import User

        user = self._create_user("existing_candidate")
        UserProfile.objects.create(user=user, role="candidate", profile_data={})

        response = self.client.post(
            reverse("login"),
            {"username": "existing_candidate", "password": "password"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "candidates/dashboard.html")

    def test_free_user_can_view_pro_checkout_option(self):
        user = self._create_user("free_plan")
        UserProfile.objects.create(user=user, role="candidate")
        self.client.force_login(user)

        response = self.client.get(reverse("plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SkillBridge Pro")
        self.assertContains(response, "sk_test_")

    def test_pro_plan_entitlement_is_active(self):
        user = self._create_user("pro_plan")
        profile = UserProfile.objects.create(user=user, role="candidate", plan="pro")

        self.assertTrue(profile.is_pro)

    def test_signup_can_skip_onboarding_and_reach_dashboard(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "skip_candidate",
                "email": "skip@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "candidate",
            },
        )
        self.assertRedirects(response, reverse("onboarding"))

        response = self.client.post(reverse("onboarding"), {"skip": "1"}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "candidates/dashboard.html")

    def test_protected_page_uses_project_login_url(self):
        response = self.client.get(reverse("candidate_jobs"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('candidate_jobs')}",
        )

    def test_existing_login_returns_to_requested_page(self):
        user = self._create_user("returning_candidate")
        UserProfile.objects.create(user=user, role="candidate", profile_data={})

        response = self.client.post(
            f"{reverse('login')}?next={reverse('candidate_jobs')}",
            {"username": "returning_candidate", "password": "password"},
        )

        self.assertRedirects(response, reverse("candidate_jobs"))

    def test_signup_skip_returns_to_requested_page(self):
        response = self.client.post(
            f"{reverse('signup')}?next=/jobs/999/",
            {
                "username": "applying_candidate",
                "email": "applying@example.com",
                "password1": "A secure password 123!",
                "password2": "A secure password 123!",
                "role": "candidate",
            },
        )
        self.assertRedirects(response, reverse("onboarding"))

        response = self.client.post(reverse("onboarding"), {"skip": "1"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/jobs/999/")
