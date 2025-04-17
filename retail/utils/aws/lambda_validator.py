import requests

from django.conf import settings

from rest_framework.response import Response
from rest_framework import status


class LambdaURLValidator:  # pragma: no cover
    """
    Validator class for AWS Lambda STS URLs and authentication.

    This class provides methods to validate STS URLs and protect resources
    by verifying AWS Lambda caller identity.
    """

    def is_valid_url(self, sts_url):
        """
        Validate if the provided STS URL is properly formatted.

        Args:
            sts_url (str): The STS URL to validate.

        Returns:
            bool: True if the URL is valid, False otherwise.
        """
        return sts_url.startswith(
            "https://sts.amazonaws.com/?Action=GetCallerIdentity&"
        ) and (".." not in sts_url)

    def protected_resource(self, request):
        """
        Protect a resource by validating AWS Lambda caller identity.

        This method extracts the STS URL from the request's Authorization header,
        validates it, and checks if the caller's ARN is in the allowed roles.

        Args:
            request: The HTTP request object containing the Authorization header.

        Returns:
            Response: A DRF Response object with appropriate status code and message.
                     200 if access is granted, 400/401 for validation errors,
                     or 500 for unexpected errors.
        """
        try:
            sts_url = request.headers.get("Authorization").split("Bearer ", 2)[1]
            if not self.is_valid_url(sts_url):
                return Response(
                    {"message": "Invalid sts"}, status=status.HTTP_400_BAD_REQUEST
                )

            response = requests.request(
                method="GET",
                url=sts_url,
                headers={"Accept": "application/json"},
                timeout=30,
            )

            identity_arn = response.json()["GetCallerIdentityResponse"][
                "GetCallerIdentityResult"
            ]["Arn"]
            if identity_arn in settings.LAMBDA_ALLOWED_ROLES:
                return Response({"message": "Access granted!", "role": identity_arn})
            else:
                return Response(
                    {"message": "Invalid arn"}, status=status.HTTP_401_UNAUTHORIZED
                )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
