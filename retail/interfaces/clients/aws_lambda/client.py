from typing import Protocol, Dict, Any


class AwsLambdaClientInterface(Protocol):
    def create_function(self, function_name: str, zip_bytes: bytes) -> Dict[str, Any]:
        ...

    def update_function_code(
        self, function_name: str, zip_bytes: bytes
    ) -> Dict[str, Any]:
        ...

    def invoke(self, function_name: str) -> Dict[str, Any]:
        ...
