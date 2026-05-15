from typing import Any, Dict, Protocol


class PaymentClientInterface(Protocol):
    def update_channel(
        self,
        channel_uuid: str,
        private_key_pem: str,
        phone_number: str,
        project_uuid: str,
        phone_number_id: str,
        waba_id: str,
    ) -> Dict[str, Any]:
        ...
