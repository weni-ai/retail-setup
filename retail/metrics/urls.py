from django.urls import path

from retail.metrics.views import RecordProductMetricEventView

urlpatterns = [
    path(
        "events/",
        RecordProductMetricEventView.as_view(),
        name="product-metric-events",
    ),
]
