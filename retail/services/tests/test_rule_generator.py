import json

from unittest.mock import Mock, patch

from django.test import TestCase

from retail.services.rule_generator import (
    RuleGenerator,
    RuleGeneratorBadRequest,
    RuleGeneratorUnprocessableEntity,
    RuleGeneratorInternalServerError,
    RuleGeneratorResponseStatusCode,
)


class RuleGeneratorTestCase(TestCase):
    def setUp(self):
        self.mock_lambda_service = Mock()
        self.rule_generator = RuleGenerator(lambda_service=self.mock_lambda_service)

    def test_generate_code_ok(self):
        response_payload = {
            "statusCode": RuleGeneratorResponseStatusCode.OK,
            "body": {"generated_code": "print('Hello World')"},
        }
        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(response_payload)))
        }

        parameters = [{"name": "param1", "value": "value1"}]
        result = self.rule_generator.generate_code(parameters)
        self.assertEqual(result, "print('Hello World')")

    def test_generate_code_bad_request(self):
        response_payload = {
            "statusCode": RuleGeneratorResponseStatusCode.BAD_REQUEST,
            "body": {"error": "Bad request error"},
        }
        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(response_payload)))
        }

        parameters = [{"name": "param1", "value": "value1"}]
        with self.assertRaises(RuleGeneratorBadRequest):
            self.rule_generator.generate_code(parameters)

    def test_generate_code_unprocessable_entity(self):
        response_payload = {
            "statusCode": RuleGeneratorResponseStatusCode.UNPROCESSABLE_ENTITY,
            "body": {"error": "Unprocessable entity error"},
        }
        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(response_payload)))
        }

        parameters = [{"name": "param1", "value": "value1"}]
        with self.assertRaises(RuleGeneratorUnprocessableEntity):
            self.rule_generator.generate_code(parameters)

    def test_generate_code_unknown_error(self):
        response_payload = {"statusCode": 999, "body": {"error": "Unknown error"}}
        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(response_payload)))
        }

        parameters = [{"name": "param1", "value": "value1"}]
        with self.assertRaises(RuleGeneratorInternalServerError):
            self.rule_generator.generate_code(parameters)

    def test_generate_code_no_status_code(self):
        response_payload = {"body": {"error": "No status code"}}
        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(response_payload)))
        }

        parameters = [{"name": "param1", "value": "value1"}]
        with self.assertRaises(RuleGeneratorInternalServerError):
            self.rule_generator.generate_code(parameters)

    def test_invoke_code_generator_with_integrated_agent(self):
        class DummyAgent:
            examples = "example data"

        class DummyIntegratedAgent:
            agent = DummyAgent()

        integrated_agent = DummyIntegratedAgent()

        response_payload = {
            "statusCode": RuleGeneratorResponseStatusCode.OK,
            "body": {"generated_code": "code with examples"},
        }
        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(response_payload)))
        }

        parameters = [{"name": "param1", "value": "value1"}]
        result = self.rule_generator.generate_code(
            parameters, integrated_agent=integrated_agent
        )
        self.assertIn({"name": "examples", "value": "example data"}, parameters)
        self.assertEqual(result, "code with examples")

    def test_invoke_code_generator_without_integrated_agent(self):
        response_payload = {
            "statusCode": RuleGeneratorResponseStatusCode.OK,
            "body": {"generated_code": "code without examples"},
        }
        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(response_payload)))
        }

        parameters = [{"name": "param1", "value": "value1"}]
        result = self.rule_generator.generate_code(parameters)
        self.assertEqual(result, "code without examples")


class RuleGeneratorRetryTestCase(TestCase):
    def setUp(self):
        self.mock_lambda_service = Mock()

    @patch("time.sleep")
    @patch("retail.services.rule_generator.service.logger")
    def test_retry_success_on_second_attempt(self, mock_logger, mock_sleep):
        rule_generator = RuleGenerator(
            lambda_service=self.mock_lambda_service,
            max_retry_attempts=1,
            retry_delay_seconds=0.5,
        )

        error_response = {
            "statusCode": RuleGeneratorResponseStatusCode.UNPROCESSABLE_ENTITY,
            "body": {"error": "AI hallucination error"},
        }
        success_response = {
            "statusCode": RuleGeneratorResponseStatusCode.OK,
            "body": {"generated_code": "print('Success on retry')"},
        }

        self.mock_lambda_service.invoke.side_effect = [
            {"Payload": Mock(read=Mock(return_value=json.dumps(error_response)))},
            {"Payload": Mock(read=Mock(return_value=json.dumps(success_response)))},
        ]

        parameters = [{"name": "param1", "value": "value1"}]
        result = rule_generator.generate_code(parameters)

        self.assertEqual(result, "print('Success on retry')")

        self.assertEqual(self.mock_lambda_service.invoke.call_count, 2)

        mock_sleep.assert_called_once_with(0.5)

        mock_logger.info.assert_any_call("Code generation attempt 1/2")
        mock_logger.warning.assert_called_once()
        mock_logger.info.assert_any_call("Code generation attempt 2/2")
        mock_logger.info.assert_any_call("Code generation succeeded on attempt 2")

    @patch("time.sleep")
    @patch("retail.services.rule_generator.service.logger")
    def test_retry_fails_all_attempts(self, mock_logger, mock_sleep):
        rule_generator = RuleGenerator(
            lambda_service=self.mock_lambda_service,
            max_retry_attempts=2,
            retry_delay_seconds=0.1,
        )

        error_response = {
            "statusCode": RuleGeneratorResponseStatusCode.BAD_REQUEST,
            "body": {"error": "Persistent error"},
        }

        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(error_response)))
        }

        parameters = [{"name": "param1", "value": "value1"}]

        with self.assertRaises(RuleGeneratorBadRequest):
            rule_generator.generate_code(parameters)

        self.assertEqual(self.mock_lambda_service.invoke.call_count, 3)

        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(0.1)

        mock_logger.error.assert_called_once()
        self.assertIn("failed after 3 attempts", str(mock_logger.error.call_args))

    def test_no_retry_on_first_success(self):
        rule_generator = RuleGenerator(
            lambda_service=self.mock_lambda_service, max_retry_attempts=2
        )

        success_response = {
            "statusCode": RuleGeneratorResponseStatusCode.OK,
            "body": {"generated_code": "print('First attempt success')"},
        }

        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(success_response)))
        }

        parameters = [{"name": "param1", "value": "value1"}]
        result = rule_generator.generate_code(parameters)

        self.assertEqual(result, "print('First attempt success')")

        self.assertEqual(self.mock_lambda_service.invoke.call_count, 1)

    @patch("time.sleep")
    def test_retry_with_different_exceptions(self, mock_sleep):
        rule_generator = RuleGenerator(
            lambda_service=self.mock_lambda_service, max_retry_attempts=1
        )

        responses = [
            {
                "statusCode": RuleGeneratorResponseStatusCode.UNPROCESSABLE_ENTITY,
                "body": {"error": "Unprocessable error"},
            },
            {
                "statusCode": 500,
                "body": {"error": "Internal error"},
            },
        ]

        self.mock_lambda_service.invoke.side_effect = [
            {"Payload": Mock(read=Mock(return_value=json.dumps(responses[0])))},
            {"Payload": Mock(read=Mock(return_value=json.dumps(responses[1])))},
        ]

        parameters = [{"name": "param1", "value": "value1"}]

        with self.assertRaises(RuleGeneratorInternalServerError):
            rule_generator.generate_code(parameters)

        self.assertEqual(self.mock_lambda_service.invoke.call_count, 2)
        mock_sleep.assert_called_once()

    def test_retry_configuration_zero_attempts(self):
        rule_generator = RuleGenerator(
            lambda_service=self.mock_lambda_service, max_retry_attempts=0
        )

        error_response = {
            "statusCode": RuleGeneratorResponseStatusCode.BAD_REQUEST,
            "body": {"error": "Error on first attempt"},
        }

        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(error_response)))
        }

        parameters = [{"name": "param1", "value": "value1"}]

        with self.assertRaises(RuleGeneratorBadRequest):
            rule_generator.generate_code(parameters)

        self.assertEqual(self.mock_lambda_service.invoke.call_count, 1)

    @patch("time.sleep")
    @patch("retail.services.rule_generator.service.logger")
    def test_retry_with_custom_delay(self, mock_logger, mock_sleep):
        custom_delay = 2.5
        rule_generator = RuleGenerator(
            lambda_service=self.mock_lambda_service,
            max_retry_attempts=1,
            retry_delay_seconds=custom_delay,
        )

        error_response = {
            "statusCode": RuleGeneratorResponseStatusCode.UNPROCESSABLE_ENTITY,
            "body": {"error": "Error"},
        }
        success_response = {
            "statusCode": RuleGeneratorResponseStatusCode.OK,
            "body": {"generated_code": "success"},
        }

        self.mock_lambda_service.invoke.side_effect = [
            {"Payload": Mock(read=Mock(return_value=json.dumps(error_response)))},
            {"Payload": Mock(read=Mock(return_value=json.dumps(success_response)))},
        ]

        parameters = [{"name": "param1", "value": "value1"}]
        result = rule_generator.generate_code(parameters)

        self.assertEqual(result, "success")
        mock_sleep.assert_called_once_with(custom_delay)

    @patch("retail.services.rule_generator.service.logger")
    def test_retry_logging_messages(self, mock_logger):
        rule_generator = RuleGenerator(
            lambda_service=self.mock_lambda_service, max_retry_attempts=1
        )

        error_response = {
            "statusCode": RuleGeneratorResponseStatusCode.BAD_REQUEST,
            "body": {"error": "Test error"},
        }

        self.mock_lambda_service.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps(error_response)))
        }

        parameters = [{"name": "param1", "value": "value1"}]

        with self.assertRaises(RuleGeneratorBadRequest):
            rule_generator.generate_code(parameters)

        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        warning_calls = [call[0][0] for call in mock_logger.warning.call_args_list]
        error_calls = [call[0][0] for call in mock_logger.error.call_args_list]

        self.assertTrue(any("attempt 1/2" in msg for msg in info_calls))
        self.assertTrue(any("attempt 2/2" in msg for msg in info_calls))
        self.assertTrue(any("failed on attempt 1" in msg for msg in warning_calls))
        self.assertTrue(any("failed after 2 attempts" in msg for msg in error_calls))
