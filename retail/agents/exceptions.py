from rest_framework.exceptions import APIException
from rest_framework import status


class AgentFileNotSent(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "agent_not_sent"
