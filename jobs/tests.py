from django.test import TestCase

from .forms import JobForm


class JobFormTests(TestCase):
    def test_salary_range_must_be_ordered(self):
        form = JobForm(data={"salary_min": 5000, "salary_max": 3000})

        self.assertFalse(form.is_valid())
        self.assertIn("salary_max", form.errors)

# Create your tests here.
