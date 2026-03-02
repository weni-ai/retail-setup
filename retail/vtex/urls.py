from django.urls import path
from retail.vtex.views import (
    AccountIdentifierProxyView,
    CreateProjectUserView,
    OrderFormTrackingView,
    OrderDetailsProxyView,
    OrdersProxyView,
    VtexProxyView,
)


urlpatterns = [
    path("orders/", OrdersProxyView.as_view(), name="vtex-orders"),
    path(
        "projects/account-identifier/",
        AccountIdentifierProxyView.as_view(),
        name="vtex-account-identifier",
    ),
    path(
        "projects/orders/<str:order_id>/",
        OrderDetailsProxyView.as_view(),
        name="vtex-order-details",
    ),
    path(
        "order-form-tracking/",
        OrderFormTrackingView.as_view(),
        name="vtex-order-form-tracking",
    ),
    path(
        "proxy/",
        VtexProxyView.as_view(),
        name="vtex-proxy",
    ),
    path(
        "account/<str:vtex_account>/project-user/",
        CreateProjectUserView.as_view(),
        name="create-project-user",
    ),
]
