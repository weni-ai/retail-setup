from unittest.mock import MagicMock, patch, mock_open

from django.test import TestCase

from retail.services.code_actions.service import CodeActionsService


class TestCodeActionsService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = CodeActionsService(client=self.mock_client)
        self.action_name = "test_action"
        self.language = "python"
        self.type = "broadcast"
        self.project_uuid = "project-uuid-123"
        self.action_id = "action-id-123"
        self.message_payload = {"message": "test message"}
        self.extra_payload = {"extra": "data"}

    def test_init(self):
        service = CodeActionsService(client=self.mock_client)
        self.assertEqual(service.client, self.mock_client)

    @patch(
        "retail.services.code_actions.service.CodeActionsService._load_action_code_template"
    )
    def test_register_code_action_success(self, mock_load_template):
        mock_template_code = "def action(): pass"
        mock_load_template.return_value = mock_template_code
        expected_response = {"action_id": self.action_id, "status": "registered"}
        self.mock_client.register_code_action.return_value = expected_response

        result = self.service.register_code_action(
            self.action_name, self.language, self.type, self.project_uuid
        )

        mock_load_template.assert_called_once_with("whatsapp_broadcast_action.py")
        self.mock_client.register_code_action.assert_called_once_with(
            self.action_name,
            mock_template_code,
            self.language,
            self.type,
            self.project_uuid,
        )
        self.assertEqual(result, expected_response)

    def test_run_code_action_with_extra_payload(self):
        expected_response = {"result": "success", "output": "action executed"}
        self.mock_client.run_code_action.return_value = expected_response

        result = self.service.run_code_action(
            self.action_id, self.message_payload, self.extra_payload
        )

        self.mock_client.run_code_action.assert_called_once_with(
            self.action_id, self.message_payload, self.extra_payload
        )
        self.assertEqual(result, expected_response)

    def test_run_code_action_without_extra_payload(self):
        expected_response = {"result": "success", "output": "action executed"}
        self.mock_client.run_code_action.return_value = expected_response

        result = self.service.run_code_action(self.action_id, self.message_payload)

        self.mock_client.run_code_action.assert_called_once_with(
            self.action_id, self.message_payload, None
        )
        self.assertEqual(result, expected_response)

    @patch("builtins.open", new_callable=mock_open, read_data="template content")
    def test_load_action_code_template_success(self, mock_file):
        filename = "test_template.py"

        result = self.service._load_action_code_template(filename)

        mock_file.assert_called_once()
        call_args = mock_file.call_args[0][0]
        self.assertTrue(call_args.endswith(f"templates/{filename}"))
        self.assertEqual(result, "template content")

    @patch("builtins.open", side_effect=FileNotFoundError())
    @patch("retail.services.code_actions.service.logger")
    def test_load_action_code_template_file_not_found(self, mock_logger, mock_file):
        filename = "nonexistent_template.py"

        with self.assertRaises(ValueError) as context:
            self.service._load_action_code_template(filename)

        mock_logger.error.assert_called_once()
        error_message = mock_logger.error.call_args[0][0]

        self.assertIn("Template file not found at:", error_message)
        self.assertIn(filename, error_message)
        self.assertIn("Template file not found at:", str(context.exception))

    @patch("builtins.open", side_effect=Exception("Permission denied"))
    @patch("retail.services.code_actions.service.logger")
    def test_load_action_code_template_other_exception(self, mock_logger, mock_file):
        filename = "template.py"

        with self.assertRaises(Exception) as context:
            self.service._load_action_code_template(filename)

        mock_logger.error.assert_called_once_with(
            "Error reading template file: Permission denied"
        )
        self.assertEqual(str(context.exception), "Permission denied")

    @patch("retail.services.code_actions.service.logger")
    def test_delete_registered_code_action_success(self, mock_logger):
        action_data = {"action1": "id-123", "action2": "id-456"}

        self.service.delete_registered_code_action(action_data)

        self.assertEqual(self.mock_client.delete_code_action.call_count, 2)
        self.mock_client.delete_code_action.assert_any_call("id-123")
        self.mock_client.delete_code_action.assert_any_call("id-456")

        self.assertEqual(mock_logger.info.call_count, 2)
        mock_logger.info.assert_any_call(
            "Deleted code action action1 (ID: id-123) successfully."
        )
        mock_logger.info.assert_any_call(
            "Deleted code action action2 (ID: id-456) successfully."
        )

    @patch("retail.services.code_actions.service.logger")
    def test_delete_registered_code_action_empty_data(self, mock_logger):
        action_data = {}

        self.service.delete_registered_code_action(action_data)

        self.mock_client.delete_code_action.assert_not_called()
        mock_logger.info.assert_not_called()
