import csv
import io

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from accounts.models import UserProfile
from employers.models import Company, RecruiterProfile
from .forms import JobForm
from .imports import IMPORT_FIELDS, read_import, template_example, template_headers, validate_import
from .models import Job


class JobImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="importer")
        UserProfile.objects.create(user=self.user, role="recruiter")
        self.company = Company.objects.create(name="Import Company")
        RecruiterProfile.objects.create(user=self.user, company=self.company)
        self.client.force_login(self.user)

    def csv_upload(self, rows=None):
        text = io.StringIO()
        writer = csv.writer(text)
        writer.writerow(template_headers())
        for row in rows or [template_example()]:
            writer.writerow([row.get(field, "") for field in IMPORT_FIELDS])
        return SimpleUploadedFile("jobs.csv", text.getvalue().encode())

    def test_csv_and_excel_templates_round_trip(self):
        for extension in ("csv", "xlsx"):
            with self.subTest(extension=extension):
                response = self.client.get(reverse("recruiter_job_template"), {"format": extension})
                self.assertEqual(response.status_code, 200)
                rows = read_import(SimpleUploadedFile("jobs." + extension, response.content))
                forms, errors = validate_import(rows)
                self.assertEqual(errors, [])
                self.assertEqual(len(forms), 1)
                self.assertEqual(forms[0].cleaned_data["required_skills"], "Python, Django, SQL")

    def test_import_requires_preview_then_confirmation_and_preserves_weights(self):
        response = self.client.post(reverse("recruiter_import_listings"), {"file": self.csv_upload()})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm and create 1 listing")
        self.assertEqual(Job.objects.count(), 0)
        token = self.client.session["job_import_preview"]["token"]
        response = self.client.post(reverse("recruiter_import_listings"), {"action": "confirm", "token": token})
        self.assertRedirects(response, reverse("recruiter_listings"))
        job = Job.objects.get()
        self.assertEqual(job.company, self.company)
        self.assertEqual(job.created_by, self.user)
        self.assertGreater(job.evidence_weights["Internship"], job.evidence_weights["Projects"])
        self.client.post(reverse("recruiter_import_listings"), {"action": "confirm", "token": token})
        self.assertEqual(Job.objects.count(), 1)

    def test_invalid_row_prevents_entire_import(self):
        invalid = {**template_example(), "title": "", "salary_min": "6000", "salary_max": "1000"}
        response = self.client.post(reverse("recruiter_import_listings"), {"file": self.csv_upload([template_example(), invalid])})
        self.assertContains(response, "Row 3")
        self.assertEqual(Job.objects.count(), 0)
        self.assertNotIn("job_import_preview", self.client.session)

    def test_wrong_token_and_company_change_do_not_publish(self):
        self.client.post(reverse("recruiter_import_listings"), {"file": self.csv_upload()})
        token = self.client.session["job_import_preview"]["token"]
        self.client.post(reverse("recruiter_import_listings"), {"action": "confirm", "token": "wrong"})
        self.assertFalse(Job.objects.exists())
        RecruiterProfile.objects.filter(user=self.user).update(company=Company.objects.create(name="Other"))
        self.client.post(reverse("recruiter_import_listings"), {"action": "confirm", "token": token})
        self.assertFalse(Job.objects.exists())

    def test_excel_formulas_are_rejected(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(template_headers())
        example = template_example()
        sheet.append([example[field] for field in IMPORT_FIELDS])
        sheet["A2"] = '=HYPERLINK("https://example.com")'
        output = io.BytesIO()
        workbook.save(output)
        with self.assertRaisesMessage(ValidationError, "Formulas"):
            read_import(SimpleUploadedFile("jobs.xlsx", output.getvalue()))

    def test_duplicate_headers_and_more_than_100_rows_are_rejected(self):
        with self.assertRaisesMessage(ValidationError, "unique"):
            read_import(SimpleUploadedFile("jobs.csv", b"title,title,employment_type\nx,y,full_time"))
        with self.assertRaisesMessage(ValidationError, "100"):
            read_import(self.csv_upload([template_example()] * 101))

    def test_candidate_cannot_import_or_download_recruiter_template(self):
        self.user.profile.role = "candidate"
        self.user.profile.save()
        for name in ("recruiter_import_listings", "recruiter_job_template"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_evidence_order_persists_through_normal_create_and_edit(self):
        form = JobForm(data=template_example())
        self.assertTrue(form.is_valid(), form.errors)
        job = form.save(commit=False)
        job.company = self.company
        job.created_by = self.user
        job.save()
        edit = JobForm(instance=job)
        self.assertEqual(edit.initial["evidence_rank_order"], "Internship,Projects,Self-proclaimed skills")
        self.assertEqual(job.evidence_weights["Internship"], 50)
