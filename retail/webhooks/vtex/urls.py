from django.urls import path

from retail.webhooks.vtex.views.order_status import OrderStatusWebhook
from .views.abandoned_cart_notification import AbandonedCartNotification


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
]
