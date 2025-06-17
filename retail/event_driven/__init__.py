from django.conf import settings

from weni.eda.eda_publisher import EDAPublisher
from weni.eda.django.connection_params import ConnectionParamsFactory

if getattr(settings, "USE_EDA", False):
    eda_publisher = EDAPublisher(ConnectionParamsFactory)
else:
    eda_publisher = None
