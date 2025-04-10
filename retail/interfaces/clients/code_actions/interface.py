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
    ) -> dict:
        """
        Registers a code action using the Code Actions API.

        Args:
            action_name (str): The name of the code action.
            action_code (str): The code of the code action.
            language (str): The language of the code action.
            type (str): The type of the code action.
            project_uuid (str): The UUID of the project.

        Returns:
            dict: Response from the API.
        """
        pass

    @abstractmethod
    def run_code_action(
        self, action_id: str, message_payload: dict, extra_payload: dict = None
    ) -> dict:
        """
        Runs a code action using the Code Actions API.

        Args:
            action_id (str): The ID of the code action to run.
            message_payload (dict): The payload to send to the code action.
            extra_payload (dict): The extra payload to send to the code action.

        Returns:
            dict: Response from the API.
        """
        pass
