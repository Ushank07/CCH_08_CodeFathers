from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from benefitbridge.core.forms import (
    AppealForm,
    CopilotForm,
    DocumentUploadForm,
    ProfileForm,
    QuickEligibilityForm,
    UserDocumentUploadForm,
)
from benefitbridge.core.models import (
    ApplicantDocument,
    EligibilityResult,
    Scheme,
    SchemeDocument,
    UserDocument,
    UserProfile,
)
from benefitbridge.core.services.ai_service import (
    generate_action_plan,
    generate_appeal_letter,
    generate_application_letter,
    generate_copilot_reply,
)
from benefitbridge.core.services.document_service import (
    applicant_vault_summary,
    document_checklist,
    sync_vault_and_scheme_documents,
)
from benefitbridge.core.services.eligibility_engine import (
    evaluate_all_schemes,
    evaluate_scheme,
    get_scheme_estimated_value,
    quick_evaluate_schemes,
    result_context,
    simulate_scheme_gap,
    summarize_results,
)


def current_profile(request):
    profile_id = request.session.get("profile_id")
    if not profile_id:
        return None
    return UserProfile.objects.filter(pk=profile_id).first()


def require_profile(request):
    profile = current_profile(request)
    if not profile:
        messages.info(request, "Create or load a profile before checking benefits.")
        return None
    return profile


def landing(request):
    profile = current_profile(request)
    active_schemes = list(Scheme.objects.filter(active=True).prefetch_related("rules", "documents"))
    featured_schemes = active_schemes[:4]
    
    # Calculate summary metrics for the landing page
    total_benefits_display = "₹2,50,000+"
    sample_categories = [
        {"key": "education", "title": "Education & Scholarships", "icon": "🎓", "count": sum(1 for s in active_schemes if s.category == "education")},
        {"key": "agriculture", "title": "Farmer & Agriculture", "icon": "🌾", "count": sum(1 for s in active_schemes if s.category == "agriculture")},
        {"key": "financial", "title": "Financial Assistance", "icon": "💳", "count": sum(1 for s in active_schemes if s.category == "financial")},
        {"key": "women_child", "title": "Women & Child Grants", "icon": "👩", "count": sum(1 for s in active_schemes if s.category == "women_child")},
        {"key": "social", "title": "Social Welfare & Aid", "icon": "🤝", "count": sum(1 for s in active_schemes if s.category == "social")},
    ]

    return render(
        request,
        "landing.html",
        {
            "profile": profile,
            "scheme_count": len(active_schemes),
            "featured_schemes": featured_schemes,
            "sample_categories": sample_categories,
            "total_benefits_display": total_benefits_display,
        },
    )


def profile_view(request):
    profile = current_profile(request)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            saved = form.save()
            request.session["profile_id"] = saved.id
            messages.success(request, "Profile saved. You can reuse this information for every eligibility check.")
            if request.POST.get("action") == "find":
                evaluate_all_schemes(saved)
                return redirect("dashboard")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile)
    return render(request, "profile.html", {"form": form, "profile": profile})


@require_POST
def load_demo_profile(request):
    profile = UserProfile.objects.filter(full_name="Ananya Deshmukh").first()
    if not profile:
        messages.error(request, "Demo data is not loaded yet. Run python manage.py seed_demo.")
        return redirect("profile")
    request.session["profile_id"] = profile.id
    evaluate_all_schemes(profile)
    messages.success(request, "Loaded the Strong Match demo profile and calculated eligibility.")
    return redirect("dashboard")


def dashboard(request):
    profile = require_profile(request)
    if not profile:
        return redirect("profile")
    results = list(
        EligibilityResult.objects.filter(profile=profile).select_related("scheme").order_by("-match_score")
    )
    if not results:
        results = evaluate_all_schemes(profile)
    counts = summarize_results(results)
    insight = None
    strong = [item for item in results if item.status == "strong"]
    if strong:
        insight = (
            f"{strong[0].scheme.name} is your strongest informational match at {strong[0].match_score}%. "
            "Review why you match, upload pending documents, then generate an action plan."
        )
    elif results:
        insight = "No strong matches yet. Complete missing profile fields or review potential matches."
    return render(
        request,
        "dashboard.html",
        {
            "profile": profile,
            "results": results,
            "counts": counts,
            "insight": insight,
            "readiness_avg": round(sum(item.readiness_score for item in results) / len(results), 1) if results else 0,
            "recommended": results[:3],
        },
    )


def scheme_catalogue(request):
    query = (request.GET.get("q") or "").strip()
    category = (request.GET.get("category") or "").strip()
    schemes = Scheme.objects.filter(active=True)
    if query:
        schemes = schemes.filter(
            Q(name__icontains=query) | Q(description__icontains=query) | Q(benefits__icontains=query)
        )
    if category:
        schemes = schemes.filter(category=category)
    profile = current_profile(request)
    result_map = {}
    if profile:
        result_map = {
            item.scheme_id: item
            for item in EligibilityResult.objects.filter(profile=profile, scheme__in=schemes)
        }
    cards = [{"scheme": scheme, "result": result_map.get(scheme.id)} for scheme in schemes]
    return render(
        request,
        "scheme_catalogue.html",
        {
            "cards": cards,
            "query": query,
            "category": category,
            "categories": Scheme.CATEGORY_CHOICES,
            "profile": profile,
        },
    )


def scheme_detail(request, pk):
    scheme = get_object_or_404(Scheme, pk=pk, active=True)
    profile = current_profile(request)
    result = None
    context_data = {}
    if profile:
        result = EligibilityResult.objects.filter(profile=profile, scheme=scheme).first()
        if not result:
            result = evaluate_scheme(profile, scheme)
        context_data = result_context(result)
    return render(
        request,
        "scheme_detail.html",
        {
            "scheme": scheme,
            "profile": profile,
            "result": result,
            **context_data,
        },
    )


def eligibility_report(request, pk):
    profile = require_profile(request)
    if not profile:
        return redirect("profile")
    scheme = get_object_or_404(Scheme, pk=pk, active=True)
    result = evaluate_scheme(profile, scheme)
    return render(
        request,
        "eligibility_report.html",
        {
            "profile": profile,
            "scheme": scheme,
            **result_context(result),
        },
    )


def documents_view(request, pk):
    profile = require_profile(request)
    if not profile:
        return redirect("profile")
    scheme = get_object_or_404(Scheme, pk=pk, active=True)
    result = evaluate_scheme(profile, scheme)
    form = DocumentUploadForm()
    return render(
        request,
        "documents.html",
        {
            "profile": profile,
            "scheme": scheme,
            "form": form,
            "checklist": document_checklist(profile, scheme),
            "result": result,
        },
    )


@require_POST
def upload_document(request, pk, document_id):
    profile = require_profile(request)
    if not profile:
        return redirect("profile")
    scheme = get_object_or_404(Scheme, pk=pk, active=True)
    required_doc = get_object_or_404(SchemeDocument, pk=document_id, scheme=scheme)
    form = DocumentUploadForm(request.POST, request.FILES)
    if form.is_valid():
        record, _created = ApplicantDocument.objects.update_or_create(
            profile=profile,
            document=required_doc,
            defaults={
                "scheme": scheme,
                "file": form.cleaned_data["file"],
                "status": "submitted",
                "original_name": form.cleaned_data["file"].name,
            },
        )
        evaluate_scheme(profile, scheme)
        messages.success(
            request,
            f"{required_doc.name} uploaded. File submission was recorded; this is not official certificate authentication.",
        )
        return redirect("documents", pk=scheme.pk)
    messages.error(request, "; ".join(form.errors.get("file", ["Upload failed."])))
    return redirect("documents", pk=scheme.pk)


def copilot(request, pk=None):
    profile = require_profile(request)
    if not profile:
        return redirect("profile")
    scheme = get_object_or_404(Scheme, pk=pk, active=True) if pk else None
    if scheme is None:
        best = EligibilityResult.objects.filter(profile=profile).order_by("-match_score").select_related("scheme").first()
        if best:
            return redirect("copilot_scheme", pk=best.scheme_id)
        messages.info(request, "Check benefits first so the copilot can use your eligibility results.")
        return redirect("dashboard")
    result = evaluate_scheme(profile, scheme)
    report = None
    form = CopilotForm()
    if request.method == "POST":
        form = CopilotForm(request.POST)
        if form.is_valid():
            report = generate_copilot_reply(profile, result, form.cleaned_data["question"])
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "ok": True,
                        "content": report.content,
                        "provider": report.provider,
                        "generated_by_ai": report.generated_by_ai,
                    }
                )
    suggestions = [
        "Why am I eligible for this scheme?",
        "Why am I not fully eligible?",
        "Which documents are missing?",
        "Which scheme should I prioritize?",
        "What should I do next?",
        "Explain this scheme in simple language.",
    ]
    return render(
        request,
        "copilot.html",
        {
            "profile": profile,
            "scheme": scheme,
            "result": result,
            "form": form,
            "report": report,
            "suggestions": suggestions,
        },
    )


def action_plan(request, pk):
    profile = require_profile(request)
    if not profile:
        return redirect("profile")
    scheme = get_object_or_404(Scheme, pk=pk, active=True)
    result = evaluate_scheme(profile, scheme)
    report = None
    if request.method == "POST":
        report = generate_action_plan(profile, result)
        messages.success(request, "Action plan generated from your current eligibility report.")
    return redirect(f"{reverse('application_assistant', args=[scheme.pk])}?focus=plan") if report else redirect(
        "application_assistant", pk=scheme.pk
    )


def application_assistant(request, pk):
    profile = require_profile(request)
    if not profile:
        return redirect("profile")
    scheme = get_object_or_404(Scheme, pk=pk, active=True)
    result = evaluate_scheme(profile, scheme)
    appeal_form = AppealForm()
    report = None
    if request.method == "POST":
        kind = request.POST.get("kind")
        if kind == "application":
            report = generate_application_letter(profile, result)
        elif kind == "appeal":
            appeal_form = AppealForm(request.POST)
            if appeal_form.is_valid():
                report = generate_appeal_letter(profile, result, appeal_form.cleaned_data["rejection_reason"])
        elif kind == "plan":
            report = generate_action_plan(profile, result)
        if report:
            messages.success(request, "Draft generated. Edit or copy it before using it unofficially.")
    latest = {
        "application": profile.ai_reports.filter(scheme=scheme, report_type="application_letter").order_by("-created_at").first(),
        "appeal": profile.ai_reports.filter(scheme=scheme, report_type="appeal_letter").order_by("-created_at").first(),
        "plan": profile.ai_reports.filter(scheme=scheme, report_type="action_plan").order_by("-created_at").first(),
    }
    return render(
        request,
        "application_assistant.html",
        {
            "profile": profile,
            "scheme": scheme,
            "result": result,
            "appeal_form": appeal_form,
            "latest": latest,
            "report": report,
            "focus": request.GET.get("focus", "application"),
        },
    )


def applicant_documents_view(request):
    profile = require_profile(request)
    if not profile:
        return redirect("profile")

    form = UserDocumentUploadForm()
    if request.method == "POST":
        form = UserDocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            user_doc = form.save(commit=False)
            user_doc.profile = profile
            uploaded_file = form.cleaned_data["file"]
            user_doc.original_name = uploaded_file.name
            user_doc.file_size = getattr(uploaded_file, "size", 0) or 0
            user_doc.status = "submitted"
            user_doc.save()

            sync_vault_and_scheme_documents(profile)
            evaluate_all_schemes(profile)
            messages.success(
                request,
                f"'{user_doc.get_document_type_display()}' was successfully stored in your Document Locker and synchronized with all matching schemes.",
            )
            return redirect("applicant_documents")
        else:
            messages.error(request, "Failed to upload document. Please check the file format and size.")

    summary = applicant_vault_summary(profile)
    return render(
        request,
        "applicant_documents.html",
        {
            "profile": profile,
            "form": form,
            "summary": summary,
        },
    )


@require_POST
def delete_applicant_document(request, doc_id):
    profile = require_profile(request)
    if not profile:
        return redirect("profile")
    doc = get_object_or_404(UserDocument, pk=doc_id, profile=profile)
    name = doc.get_document_type_display()
    doc.delete()
    sync_vault_and_scheme_documents(profile)
    evaluate_all_schemes(profile)
    messages.success(request, f"'{name}' was removed from your personal Document Locker.")
    return redirect("applicant_documents")


def gap_simulator(request, pk=None):
    profile = current_profile(request)
    active_schemes = list(Scheme.objects.filter(active=True).order_by("name"))
    if not active_schemes:
        messages.warning(request, "No active schemes found in catalogue.")
        return redirect("landing")

    selected_scheme = None
    if pk:
        selected_scheme = get_object_or_404(Scheme, pk=pk, active=True)
    else:
        if profile:
            unmet_res = EligibilityResult.objects.filter(profile=profile, status__in=["potential", "no"]).select_related("scheme").first()
            if unmet_res:
                selected_scheme = unmet_res.scheme
        if not selected_scheme:
            selected_scheme = active_schemes[0]

    base_data = {
        "age": profile.age if profile and profile.age is not None else 21,
        "gender": profile.gender if profile and profile.gender else "M",
        "state": profile.state if profile and profile.state else "ALL",
        "education_level": profile.education_level if profile and profile.education_level else "",
        "annual_income": int(profile.annual_income) if profile and profile.annual_income is not None else 200000,
        "category": profile.category if profile and profile.category else "general",
        "student_status": profile.student_status if profile else False,
        "working_status": profile.working_status if profile else False,
        "farmer_status": profile.farmer_status if profile else False,
        "disability_status": profile.disability_status if profile else False,
        "rural_status": profile.rural_status if profile else False,
    }

    req_data = request.POST if request.method == "POST" else request.GET
    simulated_data = dict(base_data)

    if "annual_income" in req_data:
        try:
            simulated_data["annual_income"] = int(req_data.get("annual_income"))
        except (ValueError, TypeError):
            pass
    elif "income" in req_data:
        try:
            simulated_data["annual_income"] = int(req_data.get("income"))
        except (ValueError, TypeError):
            pass

    if "age" in req_data:
        try:
            simulated_data["age"] = int(req_data.get("age"))
        except (ValueError, TypeError):
            pass

    if "gender" in req_data and req_data.get("gender"):
        simulated_data["gender"] = req_data.get("gender")
    if "state" in req_data and req_data.get("state"):
        simulated_data["state"] = req_data.get("state")
    if "education_level" in req_data and req_data.get("education_level"):
        simulated_data["education_level"] = req_data.get("education_level")
    if "category" in req_data and req_data.get("category"):
        simulated_data["category"] = req_data.get("category")

    for bool_field in ["student_status", "farmer_status", "rural_status", "disability_status", "working_status"]:
        if bool_field in req_data:
            val = str(req_data.get(bool_field)).lower()
            simulated_data[bool_field] = val in ["true", "1", "on", "yes"]

    baseline_sim = simulate_scheme_gap(base_data, selected_scheme)
    simulated_sim = simulate_scheme_gap(simulated_data, selected_scheme)

    if request.method == "POST" and request.POST.get("action") == "apply_profile":
        if not profile:
            profile = UserProfile.objects.create(
                full_name="Simulated Citizen",
                **simulated_data,
            )
            request.session["profile_id"] = profile.id
        else:
            for k, v in simulated_data.items():
                setattr(profile, k, v)
            profile.save()
        evaluate_all_schemes(profile)
        messages.success(request, f"Simulated parameters applied to {profile.full_name}'s profile. All scheme evaluations updated!")
        return redirect("dashboard")

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "baseline_score": baseline_sim["match_score"],
            "baseline_status": baseline_sim["status"],
            "simulated_score": simulated_sim["match_score"],
            "simulated_status": simulated_sim["status"],
            "satisfied_count": simulated_sim["satisfied_count"],
            "unmet_count": simulated_sim["unmet_count"],
            "gaps_breakdown": simulated_sim["gaps_breakdown"],
            "benefit_value": simulated_sim["estimated_benefit_value"],
            "can_bridge_easily": simulated_sim["can_bridge_easily"],
        })

    return render(
        request,
        "gap_simulator.html",
        {
            "profile": profile,
            "schemes": active_schemes,
            "selected_scheme": selected_scheme,
            "base_data": base_data,
            "simulated_data": simulated_data,
            "baseline": baseline_sim,
            "simulated": simulated_sim,
            "categories": UserProfile.CATEGORY_CHOICES,
            "education_choices": [c for c in UserProfile.EDUCATION_CHOICES if c[0]],
            "state_choices": UserProfile.STATE_CHOICES,
        },
    )


def check_eligibility_view(request):
    profile = current_profile(request)
    initial_data = {}
    if profile:
        initial_data = {
            "age": profile.age,
            "gender": profile.gender,
            "state": profile.state,
            "education_level": profile.education_level,
            "annual_income": profile.annual_income,
            "category": profile.category,
            "student_status": profile.student_status,
            "farmer_status": profile.farmer_status,
            "rural_status": profile.rural_status,
            "disability_status": profile.disability_status,
            "working_status": profile.working_status,
        }

    form = QuickEligibilityForm(request.GET or (initial_data if profile else None) or None)
    active_schemes_count = Scheme.objects.filter(active=True).count()
    evaluation_results = None
    selected_category = request.GET.get("filter_category", "").strip()

    data = {}
    if form.is_bound and form.is_valid():
        data = form.cleaned_data
    elif profile and initial_data:
        data = initial_data

    if data:
        evaluation_results = quick_evaluate_schemes(data)
        if selected_category:
            filtered = [r for r in evaluation_results["results"] if r["scheme"].category == selected_category]
            evaluation_results["results"] = filtered
            evaluation_results["strong_matches"] = [r for r in filtered if r["status"] == "strong"]
            evaluation_results["potential_matches"] = [r for r in filtered if r["status"] == "potential"]
            evaluation_results["other_matches"] = [r for r in filtered if r["status"] == "no"]

    if request.method == "POST" and request.POST.get("action") == "save_profile":
        p_form = QuickEligibilityForm(request.POST)
        if p_form.is_valid():
            c_data = p_form.cleaned_data
            if not profile:
                profile = UserProfile.objects.create(
                    full_name=request.POST.get("full_name") or "Citizen Applicant",
                    **c_data,
                )
                request.session["profile_id"] = profile.id
            else:
                for k, v in c_data.items():
                    setattr(profile, k, v)
                profile.save()
            evaluate_all_schemes(profile)
            messages.success(request, "Eligibility profile saved! All schemes recalculated on your dashboard.")
            return redirect("dashboard")

    return render(
        request,
        "check_eligibility.html",
        {
            "profile": profile,
            "form": form,
            "eval": evaluation_results,
            "scheme_categories": Scheme.CATEGORY_CHOICES,
            "selected_category": selected_category,
            "active_schemes_count": active_schemes_count,
        },
    )
