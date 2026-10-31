import os

from django.utils import timezone

from benefitbridge.core.models import AIReport


SYSTEM_GUARDRAILS = (
    "You are BenefitBridge, an informational government-scheme copilot. "
    "Use only the provided eligibility engine results. Never decide or change eligibility. "
    "Do not invent official policy, deadlines, or guaranteed approvals. "
    "Speak in clear, practical language for Indian citizens. "
    "Remind the user that final eligibility is decided by the relevant government authority."
)


def _context_block(profile, result=None, extra=""):
    lines = [
        f"Applicant name: {profile.full_name}",
        f"Age: {profile.age}",
        f"Gender: {profile.get_gender_display() if profile.gender else 'Not specified'}",
        f"State: {profile.get_state_display() if profile.state else 'Not specified'}",
        f"District: {profile.district or 'Not specified'}",
        f"Education: {profile.get_education_level_display() if profile.education_level else 'Not specified'}",
        f"Annual family income: {profile.annual_income}",
        f"Category: {profile.get_category_display() if profile.category else 'Not specified'}",
        f"Student: {'Yes' if profile.student_status else 'No'}",
        f"Working: {'Yes' if profile.working_status else 'No'}",
        f"Farmer: {'Yes' if profile.farmer_status else 'No'}",
        f"Disability: {'Yes' if profile.disability_status else 'No'}",
        f"Residence: {'Rural' if profile.rural_status else 'Urban'}",
        f"Profile completeness: {profile.completeness_score()}%",
    ]
    if result:
        details = result.details or {}
        lines.extend(
            [
                f"Scheme: {result.scheme.name}",
                f"Category: {result.scheme.get_category_display()}",
                f"Engine status: {result.get_status_display()}",
                f"Match score: {result.match_score}%",
                f"Readiness score: {result.readiness_score}%",
                f"Satisfied: {result.satisfied_conditions or 'None listed'}",
                f"Unmet or missing conditions: {result.missing_conditions or 'None listed'}",
                f"Missing documents: {result.missing_documents or 'None listed'}",
                f"Benefits: {result.scheme.benefits}",
                f"Official portal: {result.scheme.official_url or 'Not provided'}",
                f"Prototype note: {result.scheme.prototype_note}",
                f"Document details: {details.get('documents', {})}",
            ]
        )
    if extra:
        lines.append(extra)
    return "\n".join(str(item) for item in lines)


def _gemini_generate(prompt):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None, "missing_key"
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        errors = []
        for model_name in ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-latest"):
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    prompt,
                    request_options={"timeout": 20},
                )
                text = (getattr(response, "text", None) or "").strip()
                if text:
                    return text, "gemini"
            except Exception as exc:  # pragma: no cover - network/SDK variance
                errors.append(f"{model_name}: {exc}")
        return None, "unavailable"
    except Exception:
        return None, "unavailable"


def _fallback_copilot(profile, result, question):
    q = (question or "").lower()
    if not result:
        return (
            "Rule-based fallback mode\n\n"
            f"Hello {profile.full_name}. Save your profile and run a benefit check first. "
            "I can then explain match scores, missing documents, and next steps using the rule engine."
        )
    details = result.details or {}
    satisfied = details.get("satisfied") or []
    unmet = details.get("unmet") or []
    missing = details.get("missing_profile") or []
    docs = details.get("documents") or {}
    pending = docs.get("pending_mandatory") or []

    if "not" in q and "eligible" in q or "why am i not" in q:
        body = "Conditions still blocking a stronger match:\n"
        body += "\n".join(f"- {item.get('reason') or item.get('label')}" for item in unmet + missing) or "- None listed."
    elif "document" in q:
        body = "Document checklist from the engine:\n"
        body += "\n".join(f"- Pending: {item['name']}" for item in pending) or "- No mandatory documents are pending."
    elif "prioritize" in q or "which scheme" in q:
        body = (
            f"Based on the current scheme, {result.scheme.name} has a {result.match_score}% informational match "
            f"and {result.readiness_score}% application readiness. Prioritize schemes with Strong Match first, "
            "then complete missing documents on potential matches."
        )
    elif "next" in q:
        body = _fallback_action_plan(profile, result)
    else:
        why = "\n".join(f"- {item.get('reason') or item.get('label')}" for item in satisfied) or "- No satisfied conditions yet."
        body = (
            f"{result.scheme.name} is currently classified as {result.get_status_display()} "
            f"with a {result.match_score}% informational match score.\n\nWhy this result:\n{why}"
        )
    return (
        "Rule-based fallback mode\n\n"
        f"{body}\n\n"
        "This is informational guidance from BenefitBridge prototype rules. "
        "Final eligibility is decided by the relevant government authority."
    )


def _fallback_action_plan(profile, result):
    steps = []
    details = result.details if result else {}
    missing = (details or {}).get("missing_profile") or []
    pending = ((details or {}).get("documents") or {}).get("pending_mandatory") or []
    unmet = (details or {}).get("unmet") or []
    if profile.completeness_score() < 100:
        steps.append("Complete the remaining profile fields so the rule engine can score every condition.")
    for item in missing[:3]:
        steps.append(f"Add missing profile information: {item.get('reason') or item.get('label')}")
    for item in unmet[:3]:
        steps.append(f"Review this unmet condition: {item.get('label')}")
    for item in pending:
        steps.append(f"Obtain and upload your {item['name']}. Submission is not official certificate authentication.")
    steps.append("Re-open the eligibility report after updates so match and readiness scores can be recalculated.")
    if result and result.scheme.official_url:
        steps.append(f"When ready, visit the official portal: {result.scheme.official_url}")
    else:
        steps.append("Review a trusted government discovery portal such as https://www.myscheme.gov.in/ before applying.")
    numbered = "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    return (
        "Rule-based fallback mode\n\n"
        f"Personalized next steps for {profile.full_name}"
        + (f" on {result.scheme.name}" if result else "")
        + f":\n{numbered}\n\n"
        "These steps are generated from rule-engine gaps. They are not an official application sequence."
    )


def _fallback_application_letter(profile, result):
    scheme_name = result.scheme.name if result else "the selected scheme"
    return (
        "Rule-based fallback mode\n\n"
        f"To\nThe Scheme Administrator\n{scheme_name}\n\n"
        f"Subject: Application for {scheme_name}\n\n"
        f"Respected Sir/Madam,\n\n"
        f"I, {profile.full_name}, am writing to apply for {scheme_name}. "
        "This draft is based on information in my BenefitBridge profile and the prototype eligibility report. "
        f"Current informational match status: {result.get_status_display() if result else 'Not evaluated'}"
        f"{f' ({result.match_score}%)' if result else ''}.\n\n"
        "I request you to kindly consider my application as per the official scheme guidelines. "
        "I understand that BenefitBridge does not replace the official government process and that "
        "final eligibility will be decided by the competent authority.\n\n"
        "Thank you.\n\n"
        f"Yours faithfully,\n{profile.full_name}\n"
        f"{profile.district or ''} {profile.get_state_display() if profile.state else ''}\n"
        f"Date: {timezone.now().date().isoformat()}"
    )


def _fallback_appeal_letter(profile, result, rejection_reason):
    scheme_name = result.scheme.name if result else "the selected scheme"
    reason = rejection_reason.strip() if rejection_reason else "the stated rejection reason"
    return (
        "Rule-based fallback mode\n\n"
        f"To\nThe Appellate Authority\n{scheme_name}\n\n"
        f"Subject: Appeal against rejection of application for {scheme_name}\n\n"
        f"Respected Sir/Madam,\n\n"
        f"I, {profile.full_name}, respectfully appeal against the rejection of my application for {scheme_name}. "
        f"The rejection reason provided is: {reason}.\n\n"
        "This draft is prepared from my BenefitBridge profile and informational eligibility report. "
        "It does not invent additional facts and does not guarantee that the appeal will be accepted. "
        "I request a review in accordance with the official scheme rules and supporting documents I can produce.\n\n"
        "Thank you.\n\n"
        f"Yours faithfully,\n{profile.full_name}\n"
        f"Date: {timezone.now().date().isoformat()}"
    )


def generate_copilot_reply(profile, result, question):
    prompt = (
        f"{SYSTEM_GUARDRAILS}\n\nUser question:\n{question}\n\nContext:\n{_context_block(profile, result)}\n\n"
        "Answer using the engine result. If information is missing, say so."
    )
    text, provider = _gemini_generate(prompt)
    if not text:
        text = _fallback_copilot(profile, result, question)
        provider = "fallback"
    report = AIReport.objects.create(
        profile=profile,
        scheme=result.scheme if result else None,
        report_type="copilot",
        content=text,
        generated_by_ai=provider == "gemini",
        provider=provider,
    )
    return report


def generate_action_plan(profile, result):
    prompt = (
        f"{SYSTEM_GUARDRAILS}\n\nCreate a prioritized numbered action plan for becoming application-ready. "
        "Use missing profile fields, unmet conditions, and pending documents.\n\n"
        f"{_context_block(profile, result)}"
    )
    text, provider = _gemini_generate(prompt)
    if not text:
        text = _fallback_action_plan(profile, result)
        provider = "fallback"
    return AIReport.objects.create(
        profile=profile,
        scheme=result.scheme if result else None,
        report_type="action_plan",
        content=text,
        generated_by_ai=provider == "gemini",
        provider=provider,
    )


def generate_application_letter(profile, result):
    prompt = (
        f"{SYSTEM_GUARDRAILS}\n\nWrite a professional application letter. Do not invent facts. "
        "Use only applicant and scheme context.\n\n"
        f"{_context_block(profile, result)}"
    )
    text, provider = _gemini_generate(prompt)
    if not text:
        text = _fallback_application_letter(profile, result)
        provider = "fallback"
    return AIReport.objects.create(
        profile=profile,
        scheme=result.scheme if result else None,
        report_type="application_letter",
        content=text,
        generated_by_ai=provider == "gemini",
        provider=provider,
    )


def generate_appeal_letter(profile, result, rejection_reason):
    prompt = (
        f"{SYSTEM_GUARDRAILS}\n\nWrite a formal appeal letter. Do not invent facts or promise acceptance. "
        f"Rejection reason supplied by the user: {rejection_reason}\n\n"
        f"{_context_block(profile, result, extra=f'Rejection reason: {rejection_reason}')}"
    )
    text, provider = _gemini_generate(prompt)
    if not text:
        text = _fallback_appeal_letter(profile, result, rejection_reason)
        provider = "fallback"
    return AIReport.objects.create(
        profile=profile,
        scheme=result.scheme if result else None,
        report_type="appeal_letter",
        content=text,
        generated_by_ai=provider == "gemini",
        provider=provider,
    )
