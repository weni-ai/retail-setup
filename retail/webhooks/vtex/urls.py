from django.urls import path
from .views.abandoned_cart_notification import AbandonedCartNotification


urlpatterns = [
    path(
        "vtex/abandoned-cart/api/notification/",
        AbandonedCartNotification.as_view(),
        name="abandoned-cart",
    ),
]
