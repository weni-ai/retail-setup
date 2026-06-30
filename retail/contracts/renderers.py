"""Contract PDF renderer interface."""

from typing import Protocol


class ContractPdfRendererInterface(Protocol):
    def render(self, template_name: str, context: dict) -> bytes:
        ...
