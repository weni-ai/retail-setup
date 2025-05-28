from django.urls import path
from retail.vtex.views import AccountIdentifierProxyView, OrdersProxyView


urlpatterns = [
    path("orders/", OrdersProxyView.as_view(), name="vtex-orders"),
    path(
        "projects/<uuid:project_uuid>/account-identifier/",
        AccountIdentifierProxyView.as_view(),
        name="vtex-account-identifier",
    ),
]
