from weni.eda.eda_publisher import EDAPublisher
from weni.eda.django.connection_params import ConnectionParamsFactory


class IntegratedFeatureEDA:
    
    def publisher(self, body: dict):
        publisher = EDAPublisher(ConnectionParamsFactory)
        publisher.send_message(exchange="integrated-feature.topic", body=body)
