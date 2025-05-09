from typing import Protocol, Dict, Any


class AwsLambdaClientInterface(Protocol):
    def invoke(self, function_name: str, payload: bytes) -> Dict[str, Any]:
        ...
