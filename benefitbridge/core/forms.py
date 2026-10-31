from django import forms

from benefitbridge.core.models import ApplicantDocument, UserDocument, UserProfile
from benefitbridge.core.services.document_service import validate_upload


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            "full_name",
            "age",
            "gender",
            "state",
            "district",
            "education_level",
            "annual_income",
            "category",
            "student_status",
            "working_status",
            "farmer_status",
            "disability_status",
            "rural_status",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "input", "placeholder": "Full name"}),
            "age": forms.NumberInput(attrs={"class": "input", "min": 1, "max": 120}),
            "gender": forms.Select(attrs={"class": "input"}),
            "state": forms.Select(attrs={"class": "input"}),
            "district": forms.TextInput(attrs={"class": "input", "placeholder": "District"}),
            "education_level": forms.Select(attrs={"class": "input"}),
            "annual_income": forms.NumberInput(attrs={"class": "input", "min": 0, "step": "1"}),
            "category": forms.Select(attrs={"class": "input"}),
            "student_status": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "working_status": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "farmer_status": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "disability_status": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "rural_status": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }
        labels = {
            "annual_income": "Annual family income (INR)",
            "rural_status": "I live in a rural area",
            "student_status": "I am currently a student",
            "working_status": "I am currently working",
            "farmer_status": "I am a farmer",
            "disability_status": "I have a registered disability",
        }

    def clean_full_name(self):
        name = (self.cleaned_data.get("full_name") or "").strip()
        if len(name) < 3:
            raise forms.ValidationError("Enter your full name.")
        return name

    def clean_age(self):
        age = self.cleaned_data.get("age")
        if age is not None and (age < 1 or age > 120):
            raise forms.ValidationError("Enter a valid age between 1 and 120.")
        return age


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = ApplicantDocument
        fields = ["file"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "input", "accept": ".pdf,.jpg,.jpeg,.png"}),
        }

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        validate_upload(uploaded)
        return uploaded


class CopilotForm(forms.Form):
    question = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={"class": "input", "rows": 3, "placeholder": "Ask about eligibility, documents, or next steps"}),
    )


class AppealForm(forms.Form):
    rejection_reason = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "input",
                "rows": 4,
                "placeholder": "Enter the rejection reason provided to you. Do not add facts that are not true.",
            }
        ),
    )


class UserDocumentUploadForm(forms.ModelForm):
    class Meta:
        model = UserDocument
        fields = ["document_type", "custom_name", "file", "notes"]
        widgets = {
            "document_type": forms.Select(attrs={"class": "input"}),
            "custom_name": forms.TextInput(attrs={"class": "input", "placeholder": "Document title / label (optional)"}),
            "file": forms.ClearableFileInput(attrs={"class": "input", "accept": ".pdf,.jpg,.jpeg,.png"}),
            "notes": forms.TextInput(attrs={"class": "input", "placeholder": "Issuing authority, certificate no., etc. (optional)"}),
        }
        labels = {
            "document_type": "Document Type / Category",
            "custom_name": "Document Name / Label",
            "file": "Select File (PDF, JPG, PNG under 5MB)",
            "notes": "Reference / Notes",
        }

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        validate_upload(uploaded)
        return uploaded


class QuickEligibilityForm(forms.Form):
    age = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=120,
        widget=forms.NumberInput(attrs={"class": "input", "placeholder": "e.g. 21"}),
        label="Age",
    )
    gender = forms.ChoiceField(
        required=False,
        choices=[("", "Any / All")] + UserProfile.GENDER_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
        label="Gender",
    )
    state = forms.ChoiceField(
        required=False,
        choices=UserProfile.STATE_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
        label="State / Union Territory",
    )
    education_level = forms.ChoiceField(
        required=False,
        choices=[("", "Any Education Level")] + [c for c in UserProfile.EDUCATION_CHOICES if c[0]],
        widget=forms.Select(attrs={"class": "input"}),
        label="Education Level",
    )
    annual_income = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "input", "placeholder": "e.g. 200000"}),
        label="Annual Family Income (₹)",
    )
    category = forms.ChoiceField(
        required=False,
        choices=[("", "Any Social Category")] + UserProfile.CATEGORY_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
        label="Social Category",
    )
    student_status = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label="I am currently a student",
    )
    farmer_status = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label="I am a farmer / cultivator",
    )
    rural_status = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label="I reside in a rural area",
    )
    disability_status = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label="I have a registered disability",
    )
    working_status = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label="I am currently employed / working",
    )
