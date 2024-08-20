from weni.eda.eda_publisher import EDAPublisher
from weni.eda.django.connection_params import ConnectionParamsFactory


class IntegratedFeatureEDA:
    
    def publisher(self, body: dict, exchange: str):
        publisher = EDAPublisher(ConnectionParamsFactory)
        publisher.send_message(exchange=exchange, body=body)
