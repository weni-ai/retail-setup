from typing import Protocol


class AwsLambdaServiceInterface(Protocol):
    def send_file(self, file_obj: bytes, function_name: str) -> str:
        ...
