from dataclasses import dataclass

from typing import Any, Dict, Protocol, Mapping, Optional, List


@dataclass
class RequestData:
    params: Mapping[str, Any]
    payload: Mapping[Any, Any]
    ignored_official_rules: Optional[List[str]] = None
    credentials: Optional[Mapping[str, str]] = None
    project_rules: Optional[List[Dict[str, str]]] = None

    def set_credentials(self, credentials: Mapping[str, str]):
        self.credentials = credentials

    def set_ignored_official_rules(self, ignored_official_rules: List[str]):
        self.ignored_official_rules = ignored_official_rules

    def set_project_rules(self, project_rules: List[Dict[str, str]]):
        self.project_rules = project_rules


class AwsLambdaClientInterface(Protocol):
    def create_function(self, function_name: str, zip_bytes: bytes) -> Dict[str, Any]:
        ...

    def update_function_code(
        self, function_name: str, zip_bytes: bytes
    ) -> Dict[str, Any]:
        ...

    def invoke(self, function_name: str, data: RequestData) -> Dict[str, Any]:
        ...
