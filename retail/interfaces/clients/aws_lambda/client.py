from typing import Protocol, Dict, Any


class AwsLambdaClientInterface(Protocol):
    def create_function(self, function_name: str, zip_bytes: bytes) -> Dict[str, Any]:
        ...
