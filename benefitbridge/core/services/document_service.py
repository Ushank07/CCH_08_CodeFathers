from pathlib import Path

from django.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def validate_upload(uploaded_file):
    if not uploaded_file:
        raise ValidationError("Please choose a file to upload.")
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationError("Only PDF, JPG, JPEG, and PNG files are allowed.")
    content_type = getattr(uploaded_file, "content_type", "") or ""
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError("The file type is not allowed.")
    size = getattr(uploaded_file, "size", 0) or 0
    if size > MAX_UPLOAD_BYTES:
        raise ValidationError("Files must be 5 MB or smaller.")
    return True


def document_checklist(profile, scheme):
    required = list(scheme.documents.all())
    uploads = {
        item.document_id: item
        for item in profile.uploaded_documents.filter(scheme=scheme).select_related("document")
    }
    uploaded = []
    missing = []
    optional_missing = []
    for doc in required:
        record = uploads.get(doc.id)
        payload = {
            "id": doc.id,
            "name": doc.name,
            "mandatory": doc.mandatory,
            "upload": record,
            "status": record.status if record else "pending",
        }
        if record:
            uploaded.append(payload)
        elif doc.mandatory:
            missing.append(payload)
        else:
            optional_missing.append(payload)
            missing.append(payload)
    return {
        "required": required,
        "uploaded": uploaded,
        "missing": missing,
        "optional_missing": optional_missing,
        "pending_mandatory": [item for item in missing if item["mandatory"]],
    }


def readiness_score(profile, match_score, docs):
    profile_score = profile.completeness_score()
    mandatory = [doc for doc in docs["required"] if doc.mandatory]
    if mandatory:
        uploaded_mandatory = len(docs["uploaded"]) - sum(
            1 for item in docs["uploaded"] if not item["mandatory"]
        )
        uploaded_mandatory = max(0, min(uploaded_mandatory, len(mandatory)))
        document_score = (uploaded_mandatory / len(mandatory)) * 100
    else:
        document_score = 100
    score = round((match_score * 0.5) + (profile_score * 0.2) + (document_score * 0.3), 1)
    return {
        "score": score,
        "match_component": round(match_score * 0.5, 1),
        "profile_component": round(profile_score * 0.2, 1),
        "document_component": round(document_score * 0.3, 1),
        "profile_score": profile_score,
        "document_score": round(document_score, 1),
        "formula": "50% eligibility match + 20% profile completeness + 30% required documents submitted",
        "disclaimer": "A high readiness score does not mean official government approval.",
    }


VAULT_KEYWORD_MAP = {
    "identity": ["identity", "age", "aadhaar", "id", "pan", "voter"],
    "income": ["income", "salary", "earnings"],
    "caste": ["caste", "category", "community", "social"],
    "domicile": ["address", "domicile", "residence"],
    "education": ["college", "student", "marksheet", "degree", "diploma"],
    "bonafide": ["bonafide", "enrollment"],
    "land": ["land", "cultivation", "7/12", "patta", "khasra"],
    "disability": ["disability", "udid", "handicap"],
    "bank": ["bank", "passbook", "account"],
}


def infer_document_type(name):
    name_lower = (name or "").lower()
    for doc_type, keywords in VAULT_KEYWORD_MAP.items():
        if any(kw in name_lower for kw in keywords):
            return doc_type
    return "other"


def sync_vault_and_scheme_documents(profile):
    """Two-way sync: keeps personal document vault and individual scheme requirements in sync."""
    from benefitbridge.core.models import ApplicantDocument, SchemeDocument, UserDocument

    # 1. Sync legacy or direct ApplicantDocuments to UserDocument vault if missing
    existing_applicant_docs = ApplicantDocument.objects.filter(profile=profile).select_related("document", "scheme")
    vault_by_type = {doc.document_type: doc for doc in profile.vault_documents.all()}
    for app_doc in existing_applicant_docs:
        doc_type = infer_document_type(app_doc.document.name)
        if doc_type not in vault_by_type and app_doc.file:
            size = getattr(app_doc.file, "size", 0) or 0
            new_v = UserDocument.objects.create(
                profile=profile,
                document_type=doc_type,
                custom_name=app_doc.document.name,
                file=app_doc.file,
                original_name=app_doc.original_name or app_doc.document.name,
                file_size=size,
                status="submitted",
            )
            vault_by_type[doc_type] = new_v

    # 2. Sync UserDocument vault files to any SchemeDocument matching that type
    vault_docs = list(profile.vault_documents.all())
    if not vault_docs:
        return

    all_scheme_docs = SchemeDocument.objects.select_related("scheme").all()
    for v_doc in vault_docs:
        keywords = VAULT_KEYWORD_MAP.get(v_doc.document_type, [])
        custom_lower = (v_doc.custom_name or "").lower()
        for s_doc in all_scheme_docs:
            s_name = s_doc.name.lower()
            matches = any(kw in s_name for kw in keywords) or (custom_lower and custom_lower in s_name)
            if matches:
                ApplicantDocument.objects.update_or_create(
                    profile=profile,
                    document=s_doc,
                    defaults={
                        "scheme": s_doc.scheme,
                        "file": v_doc.file,
                        "status": "submitted",
                        "original_name": v_doc.original_name or v_doc.custom_name or s_doc.name,
                    },
                )


def applicant_vault_summary(profile):
    """Generates an extensive summary of all documents provided by the applicant."""
    from benefitbridge.core.models import Scheme, SchemeDocument, UserDocument

    sync_vault_and_scheme_documents(profile)
    vault_docs = list(profile.vault_documents.all().order_by("-uploaded_at"))

    # Active schemes and document requirements
    schemes = list(Scheme.objects.filter(active=True).prefetch_related("documents"))
    total_schemes = len(schemes)

    # Calculate coverage: which schemes are served by each uploaded document
    doc_coverage = []
    provided_types = {d.document_type for d in vault_docs}

    for doc in vault_docs:
        keywords = VAULT_KEYWORD_MAP.get(doc.document_type, [])
        matched_schemes = set()
        for scheme in schemes:
            for req in scheme.documents.all():
                if any(kw in req.name.lower() for kw in keywords) or (doc.custom_name and doc.custom_name.lower() in req.name.lower()):
                    matched_schemes.add(scheme.name)
        doc_coverage.append({
            "document": doc,
            "matched_schemes": sorted(list(matched_schemes)),
            "schemes_count": len(matched_schemes),
        })

    # Standard Recommended Government Checklist
    standard_checklist = [
        {"type": "identity", "name": "Identity Proof (Aadhaar / Voter ID / PAN)", "mandatory_level": "Essential"},
        {"type": "income", "name": "Income Certificate (Tehsildar / SDO)", "mandatory_level": "Essential"},
        {"type": "domicile", "name": "Domicile / Residence Certificate", "mandatory_level": "High"},
        {"type": "caste", "name": "Caste / Category Certificate (SC/ST/OBC/EWS)", "mandatory_level": "Category Specific"},
        {"type": "education", "name": "Student ID / College Marksheet", "mandatory_level": "Student Schemes"},
        {"type": "land", "name": "Land Records / Cultivation Proof (7/12 / Patta)", "mandatory_level": "Farmer Schemes"},
        {"type": "disability", "name": "Disability Certificate (UDID)", "mandatory_level": "Disability Schemes"},
        {"type": "bank", "name": "Bank Passbook Copy (DBT enabled)", "mandatory_level": "Disbursement"},
    ]

    for item in standard_checklist:
        item["uploaded"] = item["type"] in provided_types
        item["vault_item"] = next((d for d in vault_docs if d.document_type == item["type"]), None)

    uploaded_count = len(vault_docs)
    total_standard = len(standard_checklist)
    health_score = round(min(100, (sum(1 for i in standard_checklist if i["uploaded"]) / 4) * 100), 1)

    return {
        "vault_docs": vault_docs,
        "doc_coverage": doc_coverage,
        "standard_checklist": standard_checklist,
        "uploaded_count": uploaded_count,
        "health_score": min(100, health_score),
        "total_schemes": total_schemes,
    }
