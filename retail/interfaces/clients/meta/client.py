from typing import Protocol, Dict


class MetaClientInterface(Protocol):
    def get_pre_approved_template(
        self, template_name: str, language: str
    ) -> Dict[str, any]:
        ...
