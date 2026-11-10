from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Referral, UserProfile


class ProTrialTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="trial-user")
        self.profile = UserProfile.objects.create(user=self.user, role="candidate")
        self.client.force_login(self.user)

    def test_trial_is_post_only_and_available_once(self):
        self.assertEqual(self.client.get(reverse("start_pro_trial")).status_code, 405)
        self.client.post(reverse("start_pro_trial"))
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_pro)
        self.assertAlmostEqual((self.profile.plan_expires_at - self.profile.pro_trial_started_at).total_seconds(), 7 * 86400)
        end = self.profile.plan_expires_at
        self.client.post(reverse("start_pro_trial"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan_expires_at, end)
        self.profile.plan_expires_at = timezone.now() - timedelta(seconds=1)
        self.profile.save()
        self.assertFalse(self.profile.is_pro)
        self.client.post(reverse("start_pro_trial"))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_pro)

    def test_paid_pro_is_not_replaced_by_trial(self):
        self.profile.plan = "pro"
        self.profile.save()
        self.client.post(reverse("start_pro_trial"))
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.plan_expires_at)
        self.assertIsNone(self.profile.pro_trial_started_at)

    def test_trial_can_end_without_stripe_and_cannot_restart(self):
        self.client.post(reverse("start_pro_trial"))
        self.client.post(reverse("cancel_pro"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.plan, "free")
        self.client.post(reverse("start_pro_trial"))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_pro)

    def test_plans_offer_trial_without_referral_box(self):
        response = self.client.get(reverse("plans"))
        self.assertContains(response, "Start 7-day free trial")
        self.assertNotContains(response, "Refer a friend")

    def test_referral_links_no_longer_award_pro(self):
        self.client.logout()
        self.client.post(reverse("signup") + "?ref=" + self.profile.referral_code, {
            "username": "new-candidate", "email": "new@example.com", "role": "candidate",
            "password1": "DistinctPassword123!", "password2": "DistinctPassword123!",
        })
        self.assertEqual(UserProfile.objects.get(user__username="new-candidate").plan, "free")
        self.assertFalse(Referral.objects.exists())
