import json
from unittest.mock import Mock
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
