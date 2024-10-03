from abc import ABC, abstractmethod


class IntegrationsClientInterface(ABC):
    @abstractmethod
    def get_vtex_integration_detail(self, project_uuid: str):
        pass
