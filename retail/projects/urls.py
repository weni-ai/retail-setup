from rest_framework import routers
from retail.projects import views as project_views

router = routers.SimpleRouter()
router.register("projects", project_views.ProjectViewSet, basename="project")
router.register(
    "vtex-projects", project_views.ProjectVtexViewSet, basename="vtex-project"
)
