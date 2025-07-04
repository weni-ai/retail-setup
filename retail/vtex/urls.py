from django.urls import path
from retail.vtex.views import (
    AccountIdentifierProxyView,
    CartClickTrackingView,
    OrderDetailsProxyView,
    OrdersProxyView,
)


urlpatterns = [
    path("orders/", OrdersProxyView.as_view(), name="vtex-orders"),
    path(
        "projects/<uuid:project_uuid>/account-identifier/",
        AccountIdentifierProxyView.as_view(),
        name="vtex-account-identifier",
    ),
    path(
        "projects/<uuid:project_uuid>/orders/<str:order_id>/",
        OrderDetailsProxyView.as_view(),
        name="vtex-order-details",
    ),
    path(
        "projects/<uuid:project_uuid>/cart-click-tracking/",
        CartClickTrackingView.as_view(),
        name="vtex-cart-click-tracking",
    ),
]
