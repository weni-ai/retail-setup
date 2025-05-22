from dataclasses import dataclass

from typing import Any, Dict, Protocol, Mapping, Optional


@dataclass
class RequestData:
    params: Mapping[str, Any]
    payload: Mapping[Any, Any]
    credentials: Optional[Mapping[str, str]] = None

    def set_credentials(self, credentials: Mapping[str, str]):
        self.credentials = credentials


class AwsLambdaClientInterface(Protocol):
    def create_function(self, function_name: str, zip_bytes: bytes) -> Dict[str, Any]:
        ...

    def update_function_code(
        self, function_name: str, zip_bytes: bytes
    ) -> Dict[str, Any]:
        ...

    def invoke(self, function_name: str, data: RequestData) -> Dict[str, Any]:
        ...
