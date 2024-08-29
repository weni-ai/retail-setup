from retail.event_driven import eda_publisher


class IntegratedFeaturePublisher:

    def publish(self, body: dict):
        eda_publisher.send_message(exchange="integrated-feature.topic", body=body)
