from django.urls import path
from retail.vtex.views import (
    AccountIdentifierProxyView,
    OrderFormTrackingView,
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
        "order-form-tracking/",
        OrderFormTrackingView.as_view(),
        name="vtex-order-form-tracking",
    ),
]
