from rest_framework.exceptions import APIException
from rest_framework import status


class IntegrationsServerError(APIException):
    default_detail = "Unable to access Integrations API."


class CustomTemplateAlreadyExists(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
