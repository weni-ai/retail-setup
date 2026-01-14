from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions


view = get_schema_view(
    openapi.Info(
        title="Gallery API Documentation",
        default_version="v4.1.1",
        description="Documentation of the Gallery APIs",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
).with_ui("swagger")
