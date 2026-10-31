from django.urls import path

from benefitbridge.core import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/load-demo/", views.load_demo_profile, name="load_demo_profile"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("check-eligibility/", views.check_eligibility_view, name="check_eligibility"),
    path("gap-simulator/", views.gap_simulator, name="gap_simulator"),
    path("gap-simulator/<int:pk>/", views.gap_simulator, name="gap_simulator_scheme"),
    path("documents/", views.applicant_documents_view, name="applicant_documents"),
    path("documents/delete/<int:doc_id>/", views.delete_applicant_document, name="delete_applicant_document"),
    path("schemes/", views.scheme_catalogue, name="scheme_catalogue"),
    path("schemes/<int:pk>/", views.scheme_detail, name="scheme_detail"),
    path("schemes/<int:pk>/report/", views.eligibility_report, name="eligibility_report"),
    path("schemes/<int:pk>/documents/", views.documents_view, name="documents"),
    path("schemes/<int:pk>/documents/<int:document_id>/upload/", views.upload_document, name="upload_document"),
    path("copilot/", views.copilot, name="copilot"),
    path("copilot/<int:pk>/", views.copilot, name="copilot_scheme"),
    path("assistant/<int:pk>/", views.application_assistant, name="application_assistant"),
    path("assistant/<int:pk>/action-plan/", views.action_plan, name="action_plan"),
]
