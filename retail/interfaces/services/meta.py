from typing import Protocol, Dict


class MetaServiceInterface(Protocol):
    def get_pre_approved_template(
        self, template_name: str, language: str
    ) -> Dict[str, any]:
        ...
