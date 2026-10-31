from decimal import Decimal, InvalidOperation

from django.utils.text import Truncator

from benefitbridge.core.models import EligibilityResult
from benefitbridge.core.services.document_service import document_checklist, readiness_score


FIELD_LABELS = {
    "age": "Age",
    "gender": "Gender",
    "state": "State",
    "district": "District",
    "education_level": "Education level",
    "annual_income": "Annual family income",
    "category": "Category",
    "student_status": "Student status",
    "working_status": "Working status",
    "farmer_status": "Farmer status",
    "disability_status": "Disability status",
    "rural_status": "Rural / urban status",
}


def _is_missing(value):
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _as_number(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _display(profile, field_name, value):
    if field_name in {"student_status", "working_status", "farmer_status", "disability_status"}:
        return "Yes" if value else "No"
    if field_name == "rural_status":
        return "Rural" if value else "Urban"
    if field_name == "gender":
        return dict(profile.GENDER_CHOICES).get(value, value)
    if field_name == "state":
        return dict(profile.STATE_CHOICES).get(value, value)
    if field_name == "education_level":
        return dict(profile.EDUCATION_CHOICES).get(value, value)
    if field_name == "category":
        return dict(profile.CATEGORY_CHOICES).get(value, value)
    return value


def _compare(actual, operator, expected_raw):
    if operator == "in":
        options = [item.strip().lower() for item in str(expected_raw).split(",") if item.strip()]
        if isinstance(actual, bool):
            actual_text = "true" if actual else "false"
        else:
            actual_text = str(actual).strip().lower()
        return actual_text in options

    expected_bool = _as_bool(expected_raw)
    if isinstance(actual, bool) or expected_bool is not None and str(actual).lower() in {"true", "false"}:
        actual_bool = actual if isinstance(actual, bool) else _as_bool(actual)
        if actual_bool is None or expected_bool is None:
            return False
        if operator == "eq":
            return actual_bool == expected_bool
        if operator == "neq":
            return actual_bool != expected_bool

    actual_num = _as_number(actual)
    expected_num = _as_number(expected_raw)
    if actual_num is not None and expected_num is not None and operator in {"lt", "gt", "lte", "gte", "eq", "neq"}:
        if operator == "lt":
            return actual_num < expected_num
        if operator == "gt":
            return actual_num > expected_num
        if operator == "lte":
            return actual_num <= expected_num
        if operator == "gte":
            return actual_num >= expected_num
        if operator == "eq":
            return actual_num == expected_num
        if operator == "neq":
            return actual_num != expected_num

    actual_text = str(actual).strip().lower()
    expected_text = str(expected_raw).strip().lower()
    if operator == "eq":
        return actual_text == expected_text
    if operator == "neq":
        return actual_text != expected_text
    return False


def _human_rule(rule, profile):
    if rule.label:
        return rule.label
    field = FIELD_LABELS.get(rule.field_name, rule.field_name.replace("_", " "))
    expected = rule.value
    if rule.field_name in {"student_status", "working_status", "farmer_status", "disability_status"}:
        expected = "Yes" if _as_bool(rule.value) else "No"
    if rule.field_name == "rural_status":
        expected = "Rural" if _as_bool(rule.value) else "Urban"
    if rule.field_name == "state":
        expected = dict(profile.STATE_CHOICES).get(rule.value, rule.value)
        if str(rule.value).upper() in {"ALL", "ANY"}:
            expected = "Any state / national scheme"
    if rule.operator == "lte":
        return f"{field} is {expected} or less"
    if rule.operator == "lt":
        return f"{field} is less than {expected}"
    if rule.operator == "gte":
        return f"{field} is {expected} or more"
    if rule.operator == "gt":
        return f"{field} is greater than {expected}"
    if rule.operator == "in":
        return f"{field} is one of: {rule.value}"
    if rule.operator == "neq":
        return f"{field} is not {expected}"
    return f"{field} is {expected}"


def evaluate_scheme(profile, scheme):
    rules = list(scheme.rules.all())
    satisfied = []
    unmet = []
    missing = []
    optional_gaps = []

    required_failed = False
    required_missing = False

    for rule in rules:
        actual = getattr(profile, rule.field_name, None)
        description = _human_rule(rule, profile)
        if _is_missing(actual):
            item = {
                "field": rule.field_name,
                "label": description,
                "required": rule.required,
                "reason": f"{FIELD_LABELS.get(rule.field_name, rule.field_name)} is missing from your profile.",
            }
            missing.append(item)
            if rule.required:
                required_missing = True
            else:
                optional_gaps.append(item)
            continue

        passed = _compare(actual, rule.operator, rule.value)
        payload = {
            "field": rule.field_name,
            "label": description,
            "required": rule.required,
            "actual": str(_display(profile, rule.field_name, actual)),
        }
        if passed:
            payload["reason"] = f"{description} — your profile value is {payload['actual']}."
            satisfied.append(payload)
        else:
            payload["reason"] = f"{description} is not met. Your profile value is {payload['actual']}."
            unmet.append(payload)
            if rule.required:
                required_failed = True
            else:
                optional_gaps.append(payload)

    total = len(rules) or 1
    match_score = round((len(satisfied) / total) * 100, 1)

    if required_failed:
        status = "no"
    elif required_missing:
        status = "potential"
    elif match_score >= 80 and not unmet:
        status = "strong"
    elif not unmet and not missing:
        status = "strong"
    else:
        status = "potential"

    docs = document_checklist(profile, scheme)
    missing_doc_names = [item["name"] for item in docs["missing"] if item["mandatory"]]
    ready = readiness_score(profile, match_score, docs)

    serializable_docs = {
        "required": [
            {"id": d.id, "name": d.name, "mandatory": d.mandatory}
            for d in docs["required"]
        ],
        "uploaded": [
            {
                "id": item["id"],
                "name": item["name"],
                "mandatory": item["mandatory"],
                "status": item["status"],
                "original_name": item["upload"].original_name if item["upload"] else "",
            }
            for item in docs["uploaded"]
        ],
        "missing": [
            {
                "id": item["id"],
                "name": item["name"],
                "mandatory": item["mandatory"],
                "status": item["status"],
            }
            for item in docs["missing"]
        ],
        "pending_mandatory": [
            {
                "id": item["id"],
                "name": item["name"],
                "mandatory": item["mandatory"],
                "status": item["status"],
            }
            for item in docs["pending_mandatory"]
        ],
    }

    details = {
        "satisfied": satisfied,
        "unmet": unmet,
        "missing_profile": missing,
        "optional_gaps": optional_gaps,
        "documents": serializable_docs,
        "readiness": ready,
        "disclaimer": "Match percentage is an informational score from prototype rules, not an official probability of government approval.",
    }

    result, _created = EligibilityResult.objects.update_or_create(
        profile=profile,
        scheme=scheme,
        defaults={
            "match_score": match_score,
            "readiness_score": ready["score"],
            "status": status,
            "satisfied_conditions": "\n".join(item["label"] for item in satisfied),
            "missing_conditions": "\n".join(item["label"] for item in unmet + missing),
            "missing_documents": "\n".join(missing_doc_names),
            "details": details,
        },
    )
    return result


def evaluate_all_schemes(profile, schemes=None):
    from benefitbridge.core.models import Scheme

    if schemes is None:
        schemes = Scheme.objects.filter(active=True).prefetch_related("rules", "documents")
    results = [evaluate_scheme(profile, scheme) for scheme in schemes]
    results.sort(key=lambda item: (-item.match_score, item.scheme.name))
    return results


def summarize_results(results):
    counts = {"strong": 0, "potential": 0, "no": 0, "missing_documents": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
        if result.missing_documents:
            counts["missing_documents"] += 1
    counts["total"] = len(results)
    return counts


def result_context(result):
    details = result.details or {}
    return {
        "result": result,
        "scheme": result.scheme,
        "status": result.get_status_display(),
        "match_score": result.match_score,
        "readiness_score": result.readiness_score,
        "satisfied": details.get("satisfied", []),
        "unmet": details.get("unmet", []),
        "missing_profile": details.get("missing_profile", []),
        "documents": details.get("documents", {}),
        "readiness": details.get("readiness", {}),
        "disclaimer": details.get("disclaimer", ""),
        "short_why": Truncator(result.satisfied_conditions.replace("\n", "; ")).chars(180),
    }


SCHEME_VALUE_ESTIMATES = {
    "student": 25000,
    "matric": 18000,
    "farmer": 6000,
    "crop": 15000,
    "emergency": 30000,
    "disability": 20000,
    "women": 50000,
    "senior": 12000,
}


def get_scheme_estimated_value(scheme):
    name_lower = scheme.name.lower()
    for key, val in SCHEME_VALUE_ESTIMATES.items():
        if key in name_lower:
            return val
    return 15000


def simulate_scheme_gap(profile_data, scheme):
    """
    Simulates gaps for a given scheme against provided profile data (dict or UserProfile).
    Calculates exact gap delta and actionable steps to bridge the gap.
    """
    rules = list(scheme.rules.all())
    satisfied = []
    unmet = []
    missing = []
    gaps_breakdown = []

    for rule in rules:
        if isinstance(profile_data, dict):
            actual = profile_data.get(rule.field_name)
        else:
            actual = getattr(profile_data, rule.field_name, None)

        rule_label = rule.label or _human_rule(rule, profile_data if hasattr(profile_data, "GENDER_CHOICES") else None)
        field_display = FIELD_LABELS.get(rule.field_name, rule.field_name.replace("_", " "))

        if _is_missing(actual):
            item = {
                "field": rule.field_name,
                "label": rule_label,
                "required": rule.required,
                "type": "missing",
                "gap_description": f"Missing information: '{field_display}' is not specified.",
                "bridge_advice": f"Provide your {field_display.lower()} to enable verification.",
            }
            missing.append(item)
            gaps_breakdown.append(item)
            continue

        passed = _compare(actual, rule.operator, rule.value)
        actual_display = str(actual)
        if isinstance(actual, bool):
            actual_display = "Yes" if actual else "No"

        if passed:
            satisfied.append({
                "field": rule.field_name,
                "label": rule_label,
                "actual": actual_display,
                "required": rule.required,
                "status": "met",
            })
        else:
            # Calculate specific numerical or categorical gap
            gap_desc = f"Requirement not met. Currently '{actual_display}', required '{rule.value}'."
            bridge_advice = "Review eligibility criteria and update profile with verified supporting documentation."

            if rule.field_name == "annual_income":
                actual_num = _as_number(actual)
                expected_num = _as_number(rule.value)
                if actual_num and expected_num:
                    diff = actual_num - expected_num
                    if diff > 0:
                        gap_desc = f"Income ceiling exceeded by ₹{diff:,.0f} (Your income: ₹{actual_num:,.0f}, Limit: ₹{expected_num:,.0f})."
                        bridge_advice = "Check permissible tax/standard deductions, agricultural income exemptions, or verify whether the scheme considers net household taxable income on the Tehsildar certificate."

            elif rule.field_name == "age":
                actual_num = _as_number(actual)
                expected_num = _as_number(rule.value)
                if actual_num and expected_num:
                    if rule.operator in {"gte", "gt"} and actual_num < expected_num:
                        diff = expected_num - actual_num
                        gap_desc = f"Age criteria not met: {diff} year(s) below minimum age of {expected_num} (Current age: {actual_num})."
                        bridge_advice = f"You will become eligible once you turn {expected_num} years of age."
                    elif rule.operator in {"lte", "lt"} and actual_num > expected_num:
                        diff = actual_num - expected_num
                        gap_desc = f"Age ceiling exceeded by {diff} year(s) (Maximum allowed: {expected_num}, Current: {actual_num})."
                        bridge_advice = "Look for age relaxation guidelines (e.g. for reserved categories or PwD) or alternative senior/adult welfare schemes."

            elif rule.field_name == "student_status":
                gap_desc = "Scheme requires active enrollment as a student."
                bridge_advice = "Admission in an accredited school, college, or recognized distance-learning course satisfies this condition."

            elif rule.field_name == "farmer_status":
                gap_desc = "Requires status as an agricultural cultivator or farmer."
                bridge_advice = "Register on the state farmer database (e-Kisan/PM-Kisan) or provide family land revenue records (7/12 extract or Patta)."

            elif rule.field_name == "rural_status":
                gap_desc = "Scheme is exclusively targeted at rural residents."
                bridge_advice = "A domicile or residence certificate issued by Gram Panchayat / Village Officer validates rural location."

            elif rule.field_name == "disability_status":
                gap_desc = "Requires registered benchmark disability."
                bridge_advice = "Obtain an official UDID (Unique Disability ID) card or certificate from a designated government medical board."

            elif rule.field_name == "category":
                gap_desc = f"Targeted for specific social categories ({rule.value.upper()})."
                bridge_advice = "Ensure your official caste or EWS certificate from the competent Revenue authority is current."

            elif rule.field_name == "state":
                gap_desc = f"State-specific scheme for {rule.value}."
                bridge_advice = "Check equivalent welfare schemes in your state or national centrally sponsored schemes."

            gap_item = {
                "field": rule.field_name,
                "label": rule_label,
                "actual": actual_display,
                "expected": rule.value,
                "operator": rule.operator,
                "required": rule.required,
                "type": "unmet",
                "gap_description": gap_desc,
                "bridge_advice": bridge_advice,
            }
            unmet.append(gap_item)
            gaps_breakdown.append(gap_item)

    total_rules = len(rules) or 1
    match_score = round((len(satisfied) / total_rules) * 100, 1)
    status = "strong" if match_score >= 80 and not unmet else ("potential" if len(unmet) <= 1 or match_score >= 40 else "no")
    benefit_val = get_scheme_estimated_value(scheme)

    return {
        "scheme": scheme,
        "match_score": match_score,
        "status": status,
        "satisfied": satisfied,
        "unmet": unmet,
        "missing": missing,
        "gaps_breakdown": gaps_breakdown,
        "total_rules": total_rules,
        "satisfied_count": len(satisfied),
        "unmet_count": len(unmet),
        "missing_count": len(missing),
        "estimated_benefit_value": benefit_val,
        "can_bridge_easily": len(unmet) <= 2,
    }


def quick_evaluate_schemes(data):
    """
    Evaluates all schemes in-memory for instant checking.
    Works for guest users or session profiles without database mutation.
    """
    from benefitbridge.core.models import Scheme
    schemes = Scheme.objects.filter(active=True).prefetch_related("rules", "documents")

    results = []
    total_benefits = 0
    strong_count = 0
    potential_count = 0

    for scheme in schemes:
        sim = simulate_scheme_gap(data, scheme)
        sim["documents_count"] = scheme.documents.count()
        sim["mandatory_docs"] = [d.name for d in scheme.documents.filter(mandatory=True)]
        results.append(sim)

        if sim["status"] == "strong":
            strong_count += 1
            total_benefits += sim["estimated_benefit_value"]
        elif sim["status"] == "potential":
            potential_count += 1
            total_benefits += int(sim["estimated_benefit_value"] * 0.5)

    results.sort(key=lambda x: (-x["match_score"], x["scheme"].name))

    return {
        "results": results,
        "strong_matches": [r for r in results if r["status"] == "strong"],
        "potential_matches": [r for r in results if r["status"] == "potential"],
        "other_matches": [r for r in results if r["status"] == "no"],
        "total_schemes": len(results),
        "strong_count": strong_count,
        "potential_count": potential_count,
        "total_benefits": total_benefits,
    }
