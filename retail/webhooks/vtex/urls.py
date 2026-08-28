from django.urls import path

from retail.webhooks.vtex.views.order_status import OrderStatusWebhook
from .views.abandoned_cart_notification import AbandonedCartNotification
from .views.back_in_stock_notification import BackInStockNotification


urlpatterns = [
    path(
        "vtex/abandoned-cart/api/notification/",
        AbandonedCartNotification.as_view(),
        name="abandoned-cart",
    ),
    path(
        "vtex/order-status/api/notification/",
        OrderStatusWebhook.as_view(),
        name="order-status",
    ),
    path(
        "vtex/back-in-stock/api/notification/",
        BackInStockNotification.as_view(),
        name="back-in-stock",
    ),
]
