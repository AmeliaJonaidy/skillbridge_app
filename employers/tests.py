from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile

from .forms import CompanyForm
from .models import Company, RecruiterProfile


class CompanyWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="recruiter_company", password="Password123!")
        UserProfile.objects.create(user=self.user, role="recruiter")
        RecruiterProfile.objects.create(user=self.user)
        self.client.force_login(self.user)

    def test_company_industry_is_a_choice_and_logo_falls_back_to_website(self):
        form = CompanyForm(
            data={
                "name": "Example Company",
                "industry": "technology",
                "website": "example.com",
                "linkedin_url": "linkedin.com/company/example",
                "logo_url": "",
                "description": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        company = form.save()
        self.assertEqual(company.website, "https://example.com")
        self.assertIn("google.com/s2/favicons", company.logo_url)

    def test_local_company_lookup_endpoint_returns_company_data(self):
        company = Company.objects.create(name="Northstar Labs", website="https://northstar.example")

        response = self.client.get(reverse("recruiter_company_lookup"), {"q": "Northstar"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["name"], company.name)

# Create your tests here.
