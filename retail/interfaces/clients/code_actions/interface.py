from abc import ABC, abstractmethod


class CodeActionsClientInterface(ABC):
    @abstractmethod
    def register_code_action(
        self,
        action_name: str,
        action_code: str,
        language: str,
        type: str,
        project_uuid: str,
    ):
        """
        Register a code action.
        """
        pass

    @abstractmethod
    def run_code_action(self, action_id: str, payload: dict) -> dict:
        """
        Run a code action.
        """
        pass
