from typing import Protocol, Dict, Any, Optional


class AwsLambdaServiceInterface(Protocol):
    def send_file(
        self, file_obj: bytes, extra_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        ...
