from django.core.management.base import BaseCommand

from benefitbridge.core.models import EligibilityRule, Scheme, SchemeDocument, UserProfile
from benefitbridge.core.services.eligibility_engine import evaluate_all_schemes


SCHEMES = [
    {
        "name": "Prototype National Student Scholarship",
        "description": "A simplified sample scholarship for currently enrolled students with family income below a configured limit.",
        "category": "education",
        "benefits": "Informational sample benefit: tuition support up to a configured annual amount.",
        "state": "",
        "official_url": "https://scholarships.gov.in/",
        "rules": [
            ("student_status", "eq", "True", True, "Applicant is currently a student"),
            ("age", "lte", "30", True, "Age is 30 or below"),
            ("education_level", "in", "secondary,higher_secondary,graduate,postgraduate", True, "Education is secondary or higher"),
            ("annual_income", "lte", "800000", True, "Annual family income is Rs 8,00,000 or less"),
        ],
        "documents": [("College ID", True), ("Income certificate", True), ("Bonafide certificate", False)],
    },
    {
        "name": "Prototype Post-Matric Support",
        "description": "Sample post-matric assistance for students from configured social categories.",
        "category": "education",
        "benefits": "Informational sample benefit: exam-fee support and a book grant.",
        "state": "",
        "official_url": "https://scholarships.gov.in/",
        "rules": [
            ("student_status", "eq", "True", True, "Applicant is currently a student"),
            ("category", "in", "sc,st,obc,ews", True, "Category is SC, ST, OBC, or EWS"),
            ("annual_income", "lte", "250000", True, "Annual family income is Rs 2,50,000 or less"),
            ("education_level", "in", "higher_secondary,graduate,postgraduate", True, "Education is higher secondary or above"),
        ],
        "documents": [("Caste certificate", True), ("Income certificate", True), ("College ID", True)],
    },
    {
        "name": "Prototype Small Farmer Income Support",
        "description": "Sample income-support style scheme for farmers in rural areas.",
        "category": "agriculture",
        "benefits": "Informational sample benefit: seasonal income support instalments.",
        "state": "",
        "official_url": "https://pmkisan.gov.in/",
        "rules": [
            ("farmer_status", "eq", "True", True, "Applicant is a farmer"),
            ("rural_status", "eq", "True", True, "Applicant lives in a rural area"),
            ("annual_income", "lte", "600000", False, "Optional: family income is Rs 6,00,000 or less"),
        ],
        "documents": [("Land or cultivation proof", True), ("Identity document", True), ("Income certificate", False)],
    },
    {
        "name": "Prototype Crop Risk Assistance",
        "description": "Sample crop-risk assistance for working farmers.",
        "category": "agriculture",
        "benefits": "Informational sample benefit: partial premium or risk-cover guidance.",
        "state": "MH",
        "official_url": "https://www.myscheme.gov.in/",
        "rules": [
            ("farmer_status", "eq", "True", True, "Applicant is a farmer"),
            ("state", "eq", "MH", True, "Applicant is in Maharashtra for this sample rule"),
            ("working_status", "eq", "True", False, "Optional: currently working in agriculture"),
        ],
        "documents": [("Land or cultivation proof", True), ("Bank passbook copy", False)],
    },
    {
        "name": "Prototype Emergency Family Assistance",
        "description": "Sample financial assistance for lower-income households.",
        "category": "financial",
        "benefits": "Informational sample benefit: one-time support guidance for household expenses.",
        "state": "",
        "official_url": "https://www.myscheme.gov.in/",
        "rules": [
            ("annual_income", "lte", "300000", True, "Annual family income is Rs 3,00,000 or less"),
            ("age", "gte", "18", True, "Age is 18 or above"),
        ],
        "documents": [("Income certificate", True), ("Identity document", True), ("Address proof", True)],
    },
    {
        "name": "Prototype Disability Support Aid",
        "description": "Sample social-welfare aid for applicants with a registered disability.",
        "category": "social",
        "benefits": "Informational sample benefit: assistive-device or support-aid guidance.",
        "state": "",
        "official_url": "https://www.myscheme.gov.in/",
        "rules": [
            ("disability_status", "eq", "True", True, "Applicant has a registered disability"),
            ("annual_income", "lte", "800000", False, "Optional: family income is Rs 8,00,000 or less"),
        ],
        "documents": [("Disability certificate", True), ("Identity document", True)],
    },
    {
        "name": "Prototype Women Livelihood Grant",
        "description": "Sample livelihood grant for women applicants seeking self-employment support.",
        "category": "women_child",
        "benefits": "Informational sample benefit: seed-capital guidance and mentoring pointers.",
        "state": "",
        "official_url": "https://www.myscheme.gov.in/",
        "rules": [
            ("gender", "eq", "F", True, "Applicant is female"),
            ("age", "gte", "18", True, "Age is 18 or above"),
            ("age", "lte", "55", True, "Age is 55 or below"),
            ("annual_income", "lte", "500000", True, "Annual family income is Rs 5,00,000 or less"),
        ],
        "documents": [("Identity document", True), ("Income certificate", True), ("Address proof", False)],
    },
    {
        "name": "Prototype Senior Income Support",
        "description": "Sample senior-citizen income support using a simplified age rule.",
        "category": "social",
        "benefits": "Informational sample benefit: monthly income-support guidance.",
        "state": "",
        "official_url": "https://www.india.gov.in/",
        "rules": [
            ("age", "gte", "60", True, "Age is 60 or above"),
            ("annual_income", "lte", "400000", True, "Annual family income is Rs 4,00,000 or less"),
        ],
        "documents": [("Age or identity proof", True), ("Income certificate", True)],
    },
]


PROFILES = [
    {
        "full_name": "Ananya Deshmukh",
        "age": 21,
        "gender": "F",
        "state": "MH",
        "district": "Pune",
        "education_level": "graduate",
        "annual_income": 180000,
        "category": "obc",
        "student_status": True,
        "working_status": False,
        "farmer_status": False,
        "disability_status": False,
        "rural_status": False,
    },
    {
        "full_name": "Ravi Kulkarni",
        "age": 34,
        "gender": "M",
        "state": "MH",
        "district": "Nashik",
        "education_level": "secondary",
        "annual_income": None,
        "category": "general",
        "student_status": False,
        "working_status": True,
        "farmer_status": True,
        "disability_status": False,
        "rural_status": True,
    },
    {
        "full_name": "Vikram Malhotra",
        "age": 45,
        "gender": "M",
        "state": "DL",
        "district": "New Delhi",
        "education_level": "postgraduate",
        "annual_income": 1800000,
        "category": "general",
        "student_status": False,
        "working_status": True,
        "farmer_status": False,
        "disability_status": False,
        "rural_status": False,
    },
]


class Command(BaseCommand):
    help = "Seed prototype schemes, eligibility rules, documents, and demo profiles."

    def handle(self, *args, **options):
        for data in SCHEMES:
            scheme, _ = Scheme.objects.update_or_create(
                name=data["name"],
                defaults={
                    "description": data["description"],
                    "category": data["category"],
                    "benefits": data["benefits"],
                    "state": data["state"],
                    "official_url": data["official_url"],
                    "active": True,
                    "prototype_note": "Simplified prototype eligibility rules for demonstration only. Not official government policy.",
                },
            )
            for field_name, operator, value, required, label in data["rules"]:
                EligibilityRule.objects.update_or_create(
                    scheme=scheme,
                    field_name=field_name,
                    operator=operator,
                    value=value,
                    defaults={"required": required, "label": label},
                )
            for doc_name, mandatory in data["documents"]:
                SchemeDocument.objects.update_or_create(
                    scheme=scheme,
                    name=doc_name,
                    defaults={"mandatory": mandatory},
                )

        for data in PROFILES:
            profile, _ = UserProfile.objects.update_or_create(
                full_name=data["full_name"],
                defaults=data,
            )
            evaluate_all_schemes(profile)
            self.stdout.write(self.style.SUCCESS(f"Seeded profile {profile.full_name}"))

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
