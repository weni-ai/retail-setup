from django.urls import path, include


internal_urlpatterns = []


urlpatterns = [path("internals/", include(internal_urlpatterns))]
