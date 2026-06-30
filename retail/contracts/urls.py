from django.urls import path

from retail.contracts.views import RegisterContractAcceptanceView

urlpatterns = [
    path(
        "accept/",
        RegisterContractAcceptanceView.as_view(),
        name="contract-accept",
    ),
]
