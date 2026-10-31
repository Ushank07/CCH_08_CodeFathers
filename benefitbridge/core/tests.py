import os
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from benefitbridge.core.models import EligibilityRule, Scheme, SchemeDocument, UserProfile
from benefitbridge.core.services.ai_service import generate_copilot_reply
from benefitbridge.core.services.eligibility_engine import evaluate_scheme


class EligibilityEngineTests(TestCase):
    def setUp(self):
        self.scheme = Scheme.objects.create(
            name="Test Scholarship",
            description="Test scheme",
            category="education",
            benefits="Sample benefit",
            official_url="https://scholarships.gov.in/",
            active=True,
        )
        EligibilityRule.objects.create(
            scheme=self.scheme,
            field_name="student_status",
            operator="eq",
            value="True",
            required=True,
            label="Must be a student",
        )
        EligibilityRule.objects.create(
            scheme=self.scheme,
            field_name="annual_income",
            operator="lte",
            value="200000",
            required=True,
            label="Income limit",
        )
        EligibilityRule.objects.create(
            scheme=self.scheme,
            field_name="age",
            operator="lte",
            value="25",
            required=True,
            label="Age limit",
        )
        SchemeDocument.objects.create(scheme=self.scheme, name="Income certificate", mandatory=True)

        self.profile_a = UserProfile.objects.create(
            full_name="Profile A Strong",
            age=20,
            gender="F",
            state="MH",
            district="Pune",
            education_level="graduate",
            annual_income=150000,
            category="obc",
            student_status=True,
        )
        self.profile_b = UserProfile.objects.create(
            full_name="Profile B Potential",
            age=22,
            gender="F",
            state="MH",
            district="Nagpur",
            education_level="graduate",
            annual_income=None,
            category="obc",
            student_status=True,
        )
        self.profile_c = UserProfile.objects.create(
            full_name="Profile C Not Eligible",
            age=40,
            gender="M",
            state="DL",
            district="New Delhi",
            education_level="postgraduate",
            annual_income=900000,
            category="general",
            student_status=False,
        )

    def test_three_profiles_produce_different_results(self):
        result_a = evaluate_scheme(self.profile_a, self.scheme)
        result_b = evaluate_scheme(self.profile_b, self.scheme)
        result_c = evaluate_scheme(self.profile_c, self.scheme)
        self.assertEqual(result_a.status, "strong")
        self.assertGreaterEqual(result_a.match_score, 80)
        self.assertEqual(result_b.status, "potential")
        self.assertTrue(result_b.details["missing_profile"])
        self.assertEqual(result_c.status, "no")
        self.assertLess(result_c.match_score, result_a.match_score)
        self.assertNotEqual(result_a.status, result_b.status)
        self.assertNotEqual(result_b.status, result_c.status)

    def test_missing_value_is_not_a_pass(self):
        result_b = evaluate_scheme(self.profile_b, self.scheme)
        missing_fields = [item["field"] for item in result_b.details["missing_profile"]]
        self.assertIn("annual_income", missing_fields)
        self.assertLess(result_b.match_score, 100)


class WorkflowTests(TestCase):
    def setUp(self):
        self.scheme = Scheme.objects.create(
            name="Visible Scheme",
            description="A catalogue scheme",
            category="financial",
            benefits="Sample",
            official_url="https://www.myscheme.gov.in/",
            active=True,
        )
        EligibilityRule.objects.create(
            scheme=self.scheme,
            field_name="age",
            operator="gte",
            value="18",
            required=True,
        )
        SchemeDocument.objects.create(scheme=self.scheme, name="Identity document", mandatory=True)

    def test_homepage_and_catalogue(self):
        home = self.client.get(reverse("landing"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "BenefitBridge")
        catalogue = self.client.get(reverse("scheme_catalogue"))
        self.assertContains(catalogue, "Visible Scheme")
        filtered = self.client.get(reverse("scheme_catalogue"), {"q": "Visible", "category": "financial"})
        self.assertContains(filtered, "Visible Scheme")

    def test_profile_save_dashboard_and_report(self):
        response = self.client.post(
            reverse("profile"),
            {
                "full_name": "Demo User",
                "age": 24,
                "gender": "F",
                "state": "MH",
                "district": "Pune",
                "education_level": "graduate",
                "annual_income": 120000,
                "category": "obc",
                "student_status": "on",
                "action": "find",
            },
        )
        self.assertEqual(response.status_code, 302)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        report = self.client.get(reverse("eligibility_report", args=[self.scheme.pk]))
        self.assertEqual(report.status_code, 200)
        self.assertContains(report, "informational")

    def test_document_upload_updates_status(self):
        profile = UserProfile.objects.create(full_name="Uploader", age=24, gender="F", state="MH", annual_income=100000)
        session = self.client.session
        session["profile_id"] = profile.id
        session.save()
        uploaded = SimpleUploadedFile("id.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        document = self.scheme.documents.first()
        response = self.client.post(
            reverse("upload_document", args=[self.scheme.pk, document.id]),
            {"file": uploaded},
        )
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertTrue(profile.uploaded_documents.exists())
        result = evaluate_scheme(profile, self.scheme)
        self.assertEqual(result.details["documents"]["pending_mandatory"], [])

    def test_ai_fallback_without_key(self):
        profile = UserProfile.objects.create(full_name="Asker", age=20, student_status=True, annual_income=100000)
        result = evaluate_scheme(profile, self.scheme)
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            report = generate_copilot_reply(profile, result, "Why am I eligible for this scheme?")
        self.assertEqual(report.provider, "fallback")
        self.assertIn("fallback", report.content.lower())
        letter_page = self.client.get("/")
        self.assertEqual(letter_page.status_code, 200)
