"""Client for connection with code actions"""

from django.conf import settings

from retail.clients.base import RequestClient, InternalAuthentication
from retail.interfaces.clients.code_actions.interface import CodeActionsClientInterface


class CodeActionsClient(RequestClient, CodeActionsClientInterface):
    def __init__(self):
        self.base_url = settings.CODE_ACTIONS_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

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
        url = f"{self.base_url}/admin/code"

        params = {
            "name": action_name,
            "language": language,
            "type": type,
            "project": project_uuid,
        }

        response = self.make_request(
            url,
            method="POST",
            data=action_code,
            params=params,
            headers=self.authentication_instance.headers_text,
        )
        return response.json()

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
        url = f"{self.base_url}/action/endpoint/{action_id}"

        enhanced_payload = {
            "message_payload": message_payload,
            "extra_data": extra_payload,
            "token": self.authentication_instance.get_token(),
            "flows_url": settings.FLOWS_REST_ENDPOINT,
        }

        response = self.make_request(
            url,
            method="POST",
            json=enhanced_payload,
            headers=self.authentication_instance.headers,
        )
        return response.json()

    def delete_code_action(
        self,
        action_id: str,
    ) -> dict:
        """
        Deletes a code action using the Code Actions API.

        Args:
            action_id (str): ID of the code action.

        Returns:
            Response: Response object from the API.
        """
        url = f"{self.base_url}/code/{action_id}"

        response = self.make_request(
            url,
            method="DELETE",
            headers=self.authentication_instance.headers_text,
        )
        return response
