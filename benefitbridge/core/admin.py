from django.contrib import admin

from benefitbridge.core.models import (
    AIReport,
    ApplicantDocument,
    EligibilityResult,
    EligibilityRule,
    Scheme,
    SchemeDocument,
    UserProfile,
)


class EligibilityRuleInline(admin.TabularInline):
    model = EligibilityRule
    extra = 0


class SchemeDocumentInline(admin.TabularInline):
    model = SchemeDocument
    extra = 0


@admin.register(Scheme)
class SchemeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "state", "active")
    list_filter = ("category", "active")
    search_fields = ("name", "description")
    inlines = [EligibilityRuleInline, SchemeDocumentInline]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "age", "state", "category", "updated_at")
    search_fields = ("full_name", "district")


@admin.register(EligibilityResult)
class EligibilityResultAdmin(admin.ModelAdmin):
    list_display = ("profile", "scheme", "status", "match_score", "readiness_score", "updated_at")
    list_filter = ("status",)


@admin.register(ApplicantDocument)
class ApplicantDocumentAdmin(admin.ModelAdmin):
    list_display = ("profile", "scheme", "document", "status", "uploaded_at")


@admin.register(AIReport)
class AIReportAdmin(admin.ModelAdmin):
    list_display = ("profile", "scheme", "report_type", "provider", "created_at")
    list_filter = ("report_type", "provider")


admin.site.register(EligibilityRule)
admin.site.register(SchemeDocument)
