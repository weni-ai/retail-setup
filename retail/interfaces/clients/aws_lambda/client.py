from dataclasses import dataclass
from typing import Any, Dict, Protocol


@dataclass
class RequestData:
    params: dict
    payload: dict
    credentials: dict


class AwsLambdaClientInterface(Protocol):
    def create_function(self, function_name: str, zip_bytes: bytes) -> Dict[str, Any]:
        ...

    def update_function_code(
        self, function_name: str, zip_bytes: bytes
    ) -> Dict[str, Any]:
        ...

    def invoke(self, function_name: str, data: RequestData) -> Dict[str, Any]:
        ...
