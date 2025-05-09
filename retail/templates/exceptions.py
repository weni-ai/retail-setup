from rest_framework.exceptions import APIException


class IntegrationsServerError(APIException):
    default_detail = "Unable to access Integrations API."
