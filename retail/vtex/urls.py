from django.urls import path
from retail.vtex.views import OrdersProxyView


urlpatterns = [
    path("orders/", OrdersProxyView.as_view(), name="vtex-orders"),
]
