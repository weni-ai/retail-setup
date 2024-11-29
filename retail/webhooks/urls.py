from django.urls import path, include

urlpatterns = [
    path("webhook/", include("retail.webhooks.vtex.urls")),
]
