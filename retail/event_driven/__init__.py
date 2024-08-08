from weni.eda.eda_publisher import EDAPublisher
from weni.eda.django.connection_params import ConnectionParamsFactory


eda_publisher = EDAPublisher(ConnectionParamsFactory)
