import logging

from dataclasses import dataclass

from typing import List

from rest_framework.exceptions import APIException, ValidationError

from retail.api.onboard.usecases.dto import ActivateWebchatDTO
from retail.services.integrations.service import IntegrationsService
from retail.services.webchat_push.service import WebchatPublishError, WebchatPushService

logger = logging.getLogger(__name__)


@dataclass
class PublishWebchatResult:
    script_urls: List[str]

    def to_dict(self) -> dict:
        return {"script_urls": self.script_urls}


class PublishWebchatScriptUseCase:
    def __init__(
        self,
        integrations_service: IntegrationsService,
        webchat_push_service: WebchatPushService,
    ):
        self._integrations_service = integrations_service
        self._webchat_push_service = webchat_push_service

    def execute(self, dto: ActivateWebchatDTO) -> PublishWebchatResult:
        logger.info(
            f"Starting webchat activation for app_uuid={dto.app_uuid} "
            f"account_id={dto.account_id} "
            f"vtex_account={dto.vtex_account}"
        )

        script_url = self._get_wwc_script_url(dto.app_uuid)

        logger.info(
            f"Retrieved WWC script URL for app_uuid={dto.app_uuid}: {script_url}"
        )

        try:
            uploaded_urls = self._webchat_push_service.publish_webchat_script(
                script_url=script_url,
                account_id=dto.account_id,
                vtex_account=dto.vtex_account,
            )
        except WebchatPublishError as exc:
            logger.error(
                f"Failed to publish webchat script for app_uuid={dto.app_uuid} "
                f"account_id={dto.account_id} "
                f"vtex_account={dto.vtex_account} "
                f"error={exc}"
            )
            raise APIException(
                detail="Failed to publish webchat script. Please try again later."
            )

        logger.info(
            f"Webchat script published successfully for app_uuid={dto.app_uuid} at {uploaded_urls}"
        )

        return PublishWebchatResult(script_urls=uploaded_urls)

    def _get_wwc_script_url(self, app_uuid: str) -> str:
        app_data = self._integrations_service.get_channel_app(
            apptype="wwc", app_uuid=app_uuid
        )
        if not app_data:
            raise ValidationError(
                {"app_uuid": "Could not retrieve WWC app from Integrations."}
            )

        # TODO(security): validate that this app belongs to the caller's
        # project (bound to the token's vtex_account) to prevent activating a
        # channel app from another project. Blocked on confirming that the
        # Integrations get_channel_app response exposes the app's project
        # (e.g. "project" / "project_uuid"); wire the comparison once the
        # field is available.

        script_url = app_data.get("config", {}).get("script")
        if not script_url:
            raise ValidationError(
                {"app_uuid": "WWC app does not have a configured script."}
            )

        return script_url
