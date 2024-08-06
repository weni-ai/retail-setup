from django.contrib.admin.sites import AdminSite as DjangoAdminSite
from django.contrib.auth.models import User, Group
from django.urls.resolvers import URLResolver

from .urls import urlpatterns


class AdminSite(DjangoAdminSite):
    site_header = "Retail Setup"
    site_title = "Retail Setup"

    def _unregister_default_models(self) -> None:
        self.unregister(Group)
        self.unregister(User)

    def get_urls(self) -> list[URLResolver]:
        self._unregister_default_models()

        urls = super().get_urls()
        return urlpatterns + urls
