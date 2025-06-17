from rest_framework.exceptions import APIException
from rest_framework import status


class IntegrationsServerError(APIException):
    default_detail = "Unable to access Integrations API."


class CodeGeneratorBadRequest(APIException):
    status_code = status.HTTP_400_BAD_REQUEST


class CodeGeneratorUnprocessableEntity(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class CodeGeneratorInternalServerError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
