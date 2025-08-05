from rest_framework.exceptions import APIException
from rest_framework import status


class AgentFileNotSent(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "agent_not_sent"


class InvalidExamplesFormat(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_examples_format"


class GlobalRuleBadRequest(APIException):
    status_code = status.HTTP_400_BAD_REQUEST


class GlobalRuleUnprocessableEntity(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class GlobalRuleInternalServerError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
