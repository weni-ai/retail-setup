from retail.interfaces.clients.code_actions.interface import CodeActionsClientInterface


class CodeActionsService:
    def __init__(self, client: CodeActionsClientInterface):
        self.client = client

    def register_code_action(
        self,
        action_name: str,
        action_code: str,
        language: str,
        type: str,
        project_uuid: str,
    ) -> dict:
        """
        Register a code action.
        """
        return self.client.register_code_action(
            action_name, action_code, language, type, project_uuid
        )

    def run_code_action(self, action_id: str, message_payload: dict, extra_payload: dict = None) -> dict:
        """
        Run a code action.
        """
        return self.client.run_code_action(action_id, message_payload, extra_payload)
