from django.urls import path, include


urlpatterns = [
    path("webhook/", include("retail.webhooks.vtex.urls")),
    path("webhook/", include("retail.webhooks.templates.urls")),
]
