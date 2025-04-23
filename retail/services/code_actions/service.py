import os
import logging

from retail.interfaces.clients.code_actions.interface import CodeActionsClientInterface


logger = logging.getLogger(__name__)


class CodeActionsService:
    def __init__(self, client: CodeActionsClientInterface):
        self.client = client

    def register_code_action(
        self,
        action_name: str,
        language: str,
        type: str,
        project_uuid: str,
    ) -> dict:
        """
        Register a code action.
        """
        action_code = self._load_action_code_template("whatsapp_broadcast_action.py")
        return self.client.register_code_action(
            action_name, action_code, language, type, project_uuid
        )

    def run_code_action(
        self, action_id: str, message_payload: dict, extra_payload: dict = None
    ) -> dict:
        """
        Run a code action.
        """
        return self.client.run_code_action(action_id, message_payload, extra_payload)

    def _load_action_code_template(self, filename: str) -> str:
        """
        Load a code action template from the templates directory.

        Args:
            filename: The name of the template file to load

        Returns:
            The content of the template file as a string

        Raises:
            ValueError: If the template file cannot be found or read
        """
        template_path = os.path.join(os.path.dirname(__file__), "templates", filename)
        try:
            with open(template_path, "r") as file:
                return file.read()
        except FileNotFoundError:
            logger.error(f"Template file not found at: {template_path}")
            raise ValueError(f"Template file not found at: {template_path}")
        except Exception as e:
            logger.error(f"Error reading template file: {str(e)}")
            raise

    def delete_registered_code_action(self, action_data: dict) -> None:
        """
        Deletes a previously registered code action for the given integrated feature.
        """
        for name, action_id in action_data.items():
            self.client.delete_code_action(action_id)
            logger.info(f"Deleted code action {name} (ID: {action_id}) successfully.")
