from django.urls import path, include
from rest_framework.routers import SimpleRouter
from retail.projects import views as project_views


router = SimpleRouter()
router.register("projects", project_views.ProjectViewSet, basename="project")
router.register(
    "vtex-projects", project_views.ProjectVtexViewSet, basename="vtex-project"
)

urlpatterns = [
    path("", include(router.urls)),
    path(
        "projects/vtex-account/",
        project_views.VtexAccountLookupView.as_view(),
        name="project-vtex-account-lookup",
    ),
    path(
        "onboard/<str:vtex_account>/start-crawling/",
        project_views.StartOnboardingView.as_view(),
        name="onboarding-start-crawling",
    ),
    path(
        "onboard/<uuid:onboarding_uuid>/webhook/",
        project_views.CrawlerWebhookView.as_view(),
        name="onboarding-crawler-webhook",
    ),
    path(
        "onboard/<str:vtex_account>/status/",
        project_views.OnboardingStatusView.as_view(),
        name="onboarding-status",
    ),
    path(
        "onboard/<str:vtex_account>/",
        project_views.OnboardingPatchView.as_view(),
        name="onboarding-patch",
    ),
]
