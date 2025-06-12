from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from django.core.files.uploadedfile import UploadedFile
from django.test import TestCase

from rest_framework.exceptions import APIException

from retail.services.aws_lambda.service import AwsLambdaService


class TestAwsLambdaService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = AwsLambdaService(client=self.mock_client)
        self.function_name = "test-function"
        self.mock_file = MagicMock(spec=UploadedFile)
        self.mock_file.read.return_value = b"zip_content"

    def test_init_with_client(self):
        service = AwsLambdaService(client=self.mock_client)
        self.assertEqual(service.client, self.mock_client)

    @patch("retail.services.aws_lambda.service.AwsLambdaClient")
    def test_init_without_client(self, mock_aws_lambda_client):
        service = AwsLambdaService()
        mock_aws_lambda_client.assert_called_once()
        self.assertEqual(service.client, mock_aws_lambda_client.return_value)

    @patch("retail.services.aws_lambda.service.logger")
    def test_send_file_create_function_success(self, mock_logger):
        expected_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
        self.mock_client.create_function.return_value = {"FunctionArn": expected_arn}

        result = self.service.send_file(self.mock_file, self.function_name)

        self.mock_file.read.assert_called_once()
        self.mock_client.create_function.assert_called_once_with(
            function_name=self.function_name,
            zip_bytes=b"zip_content",
        )
        mock_logger.info.assert_called_once_with(
            f"Created Lambda: {self.function_name}"
        )
        self.assertEqual(result, expected_arn)

    @patch("retail.services.aws_lambda.service.logger")
    def test_send_file_update_function_on_conflict(self, mock_logger):
        expected_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
        conflict_error = ClientError(
            error_response={"Error": {"Code": "ResourceConflictException"}},
            operation_name="CreateFunction",
        )
        self.mock_client.create_function.side_effect = conflict_error
        self.mock_client.update_function_code.return_value = {
            "FunctionArn": expected_arn
        }

        result = self.service.send_file(self.mock_file, self.function_name)

        self.mock_file.read.assert_called_once()
        self.mock_client.create_function.assert_called_once_with(
            function_name=self.function_name,
            zip_bytes=b"zip_content",
        )
        self.mock_client.update_function_code.assert_called_once_with(
            function_name=self.function_name,
            zip_bytes=b"zip_content",
        )
        mock_logger.info.assert_called_once_with(
            f"Updated Lambda: {self.function_name}"
        )
        self.assertEqual(result, expected_arn)

    def test_send_file_raises_api_exception_on_other_client_error(self):
        other_error = ClientError(
            error_response={"Error": {"Code": "AccessDeniedException"}},
            operation_name="CreateFunction",
        )
        self.mock_client.create_function.side_effect = other_error

        with self.assertRaises(APIException) as context:
            self.service.send_file(self.mock_file, self.function_name)

        self.assertEqual(
            str(context.exception), "Failed to create function in aws lambda."
        )
        self.mock_file.read.assert_called_once()
        self.mock_client.create_function.assert_called_once_with(
            function_name=self.function_name,
            zip_bytes=b"zip_content",
        )
        self.mock_client.update_function_code.assert_not_called()

    def test_invoke(self):
        payload = {"key": "value"}
        expected_response = {"StatusCode": 200, "Payload": "response_data"}
        self.mock_client.invoke.return_value = expected_response

        result = self.service.invoke(self.function_name, payload)

        self.mock_client.invoke.assert_called_once_with(
            function_name=self.function_name, payload=payload
        )
        self.assertEqual(result, expected_response)
