from retail.event_driven import eda_publisher


class RemovedFeaturePublisher:

    def publish(self, body: dict):
        eda_publisher.send_message(exchange="removed-feature.topic", body=body)
