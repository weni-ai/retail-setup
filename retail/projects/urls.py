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
]
