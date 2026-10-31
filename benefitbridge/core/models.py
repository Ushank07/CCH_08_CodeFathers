from django.db import models


class UserProfile(models.Model):
    GENDER_CHOICES = [
        ("M", "Male"),
        ("F", "Female"),
        ("O", "Other"),
    ]
    CATEGORY_CHOICES = [
        ("general", "General"),
        ("ews", "EWS"),
        ("obc", "OBC"),
        ("sc", "SC"),
        ("st", "ST"),
    ]
    STATE_CHOICES = [
        ("ALL", "Any / Not specified"),
        ("MH", "Maharashtra"),
        ("KA", "Karnataka"),
        ("TN", "Tamil Nadu"),
        ("UP", "Uttar Pradesh"),
        ("GJ", "Gujarat"),
        ("RJ", "Rajasthan"),
        ("KL", "Kerala"),
        ("WB", "West Bengal"),
        ("DL", "Delhi"),
        ("PB", "Punjab"),
        ("MP", "Madhya Pradesh"),
        ("HR", "Haryana"),
        ("BR", "Bihar"),
        ("TS", "Telangana"),
        ("AP", "Andhra Pradesh"),
    ]
    EDUCATION_CHOICES = [
        ("", "Not specified"),
        ("none", "No formal education"),
        ("primary", "Primary"),
        ("secondary", "Secondary"),
        ("higher_secondary", "Higher secondary"),
        ("graduate", "Graduate"),
        ("postgraduate", "Postgraduate"),
    ]

    full_name = models.CharField(max_length=200)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    state = models.CharField(max_length=50, choices=STATE_CHOICES, blank=True)
    district = models.CharField(max_length=100, blank=True)
    education_level = models.CharField(max_length=20, choices=EDUCATION_CHOICES, blank=True)
    annual_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, blank=True)
    student_status = models.BooleanField(default=False)
    working_status = models.BooleanField(default=False)
    farmer_status = models.BooleanField(default=False)
    disability_status = models.BooleanField(default=False)
    rural_status = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.full_name}"

    def completeness_score(self):
        checks = [
            bool(self.full_name),
            self.age is not None,
            bool(self.gender),
            bool(self.state) and self.state != "ALL",
            bool(self.district),
            bool(self.education_level),
            self.annual_income is not None,
            bool(self.category),
        ]
        filled = sum(1 for item in checks if item)
        return round((filled / len(checks)) * 100, 1)


class Scheme(models.Model):
    CATEGORY_CHOICES = [
        ("education", "Education and Scholarships"),
        ("agriculture", "Agriculture"),
        ("financial", "Financial Assistance"),
        ("social", "Social Welfare"),
        ("women_child", "Women and Child Welfare"),
        ("other", "Other Government Benefits"),
    ]
    name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    benefits = models.TextField()
    state = models.CharField(max_length=50, blank=True, default="")
    official_url = models.URLField(blank=True, default="")
    active = models.BooleanField(default=True)
    prototype_note = models.TextField(
        blank=True,
        default="Simplified prototype eligibility rules for demonstration only. Not official government policy.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class EligibilityRule(models.Model):
    OPERATOR_CHOICES = [
        ("eq", "Equals"),
        ("neq", "Not Equals"),
        ("lt", "Less Than"),
        ("gt", "Greater Than"),
        ("lte", "Less Than or Equal"),
        ("gte", "Greater Than or Equal"),
        ("in", "In List"),
    ]
    FIELD_CHOICES = [
        ("age", "Age"),
        ("gender", "Gender"),
        ("state", "State"),
        ("district", "District"),
        ("education_level", "Education"),
        ("annual_income", "Annual family income"),
        ("category", "Category"),
        ("student_status", "Student status"),
        ("working_status", "Working status"),
        ("farmer_status", "Farmer status"),
        ("disability_status", "Disability status"),
        ("rural_status", "Rural / urban status"),
    ]

    scheme = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name="rules")
    field_name = models.CharField(max_length=50, choices=FIELD_CHOICES)
    operator = models.CharField(max_length=3, choices=OPERATOR_CHOICES)
    value = models.CharField(max_length=200)
    required = models.BooleanField(default=True)
    label = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.scheme.name}: {self.field_name} {self.operator} {self.value}"


class SchemeDocument(models.Model):
    scheme = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name="documents")
    name = models.CharField(max_length=100)
    mandatory = models.BooleanField(default=True)

    class Meta:
        unique_together = ("scheme", "name")

    def __str__(self):
        return f"{self.scheme.name} – {self.name}"


class ApplicantDocument(models.Model):
    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("needs_attention", "Needs attention"),
    ]
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="uploaded_documents")
    scheme = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name="applicant_documents")
    document = models.ForeignKey(SchemeDocument, on_delete=models.CASCADE)
    file = models.FileField(upload_to="scheme_documents/")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="submitted")
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("profile", "document")

    def __str__(self):
        return f"{self.profile.full_name} - {self.document.name}"


class UserDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ("identity", "Identity Proof (Aadhaar / Voter ID / PAN)"),
        ("income", "Income Certificate"),
        ("caste", "Caste / Category Certificate"),
        ("domicile", "Domicile / Address Proof"),
        ("education", "College / Student ID or Marksheet"),
        ("bonafide", "Bonafide Certificate"),
        ("land", "Land Records / Cultivation Proof (7/12 / Patta)"),
        ("disability", "Disability Certificate (UDID)"),
        ("bank", "Bank Passbook Copy"),
        ("other", "Other Supporting Document"),
    ]
    STATUS_CHOICES = [
        ("verified", "Format Verified"),
        ("submitted", "Submitted"),
        ("needs_attention", "Needs Attention"),
    ]
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="vault_documents")
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES, default="identity")
    custom_name = models.CharField(max_length=150, blank=True)
    file = models.FileField(upload_to="scheme_documents/")
    original_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="submitted")
    notes = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        name = self.custom_name or self.get_document_type_display() or self.original_name
        return f"{self.profile.full_name} - {name}"

    def file_size_display(self):
        if not self.file_size:
            try:
                if self.file and self.file.size:
                    self.file_size = self.file.size
                    self.save(update_fields=["file_size"])
            except Exception:
                return "N/A"
        size = self.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{round(size / 1024, 1)} KB"
        else:
            return f"{round(size / (1024 * 1024), 2)} MB"

    def file_extension(self):
        import os
        name = self.original_name or (self.file.name if self.file else "")
        ext = os.path.splitext(name)[1].lower().replace(".", "")
        return ext.upper() if ext else "FILE"


class EligibilityResult(models.Model):
    MATCH_STATUS_CHOICES = [
        ("strong", "Strong Match"),
        ("potential", "Potentially Eligible"),
        ("no", "Not Eligible"),
    ]
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="eligibility_results")
    scheme = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name="eligibility_results")
    match_score = models.FloatField()
    readiness_score = models.FloatField(default=0)
    status = models.CharField(max_length=10, choices=MATCH_STATUS_CHOICES)
    satisfied_conditions = models.TextField(blank=True)
    missing_conditions = models.TextField(blank=True)
    missing_documents = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("profile", "scheme")
        ordering = ["-match_score", "scheme__name"]

    def __str__(self):
        return f"{self.profile.full_name} - {self.scheme.name} ({self.status})"


class AIReport(models.Model):
    REPORT_TYPE_CHOICES = [
        ("copilot", "Copilot"),
        ("action_plan", "Action Plan"),
        ("application_letter", "Application Letter"),
        ("appeal_letter", "Appeal Letter"),
    ]
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="ai_reports")
    scheme = models.ForeignKey(Scheme, on_delete=models.CASCADE, null=True, blank=True, related_name="ai_reports")
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    content = models.TextField()
    generated_by_ai = models.BooleanField(default=False)
    provider = models.CharField(max_length=20, default="fallback")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.profile.full_name} - {self.get_report_type_display()}"
