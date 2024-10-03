from abc import ABC, abstractmethod


class FlowsClientInterface(ABC):
    @abstractmethod
    def get_user_api_token(self, user_email: str, project_uuid: str):
        pass
