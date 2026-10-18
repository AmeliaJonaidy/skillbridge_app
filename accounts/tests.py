from django.test import TestCase

from django.urls import reverse

from .forms import SignupForm
from .models import UserProfile


class AccountOnboardingTests(TestCase):
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

    def test_candidate_onboarding_starts_with_name_and_is_text_only(self):
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

        self.assertContains(response, "What should we call you?")
        self.assertNotContains(response, "Upload your current resume")
        self.assertNotContains(response, 'type="file"')
        self.assertNotContains(response, "multipart/form-data")

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

        response = self.client.post(reverse("onboarding"), {"name": "Alex Tan"})

        self.assertRedirects(response, reverse("onboarding"))
        self.assertEqual(
            UserProfile.objects.get(user__username="candidate").profile_data["name"],
            "Alex Tan",
        )
