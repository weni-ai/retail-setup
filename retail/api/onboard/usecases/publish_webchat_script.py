import logging

from dataclasses import dataclass

from rest_framework.exceptions import APIException, ValidationError

from retail.api.onboard.usecases.dto import ActivateWebchatDTO
from retail.services.integrations.service import IntegrationsService
from retail.services.webchat_push.service import WebchatPublishError, WebchatPushService

logger = logging.getLogger(__name__)


@dataclass
class PublishWebchatResult:
    script_url: str

    def to_dict(self) -> dict:
        return {"script_url": self.script_url}


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
            f"account_id={dto.account_id}"
        )

        script_url = self._get_wwc_script_url(dto.app_uuid)

        logger.info(
            f"Retrieved WWC script URL for app_uuid={dto.app_uuid}: {script_url}"
        )

        try:
            uploaded_url = self._webchat_push_service.publish_webchat_script(
                script_url=script_url,
                account_id=dto.account_id,
            )
        except WebchatPublishError as exc:
            logger.error(
                f"Failed to publish webchat script for app_uuid={dto.app_uuid} "
                f"account_id={dto.account_id}: {exc}"
            )
            raise APIException(
                detail="Failed to publish webchat script. Please try again later."
            )

        logger.info(
            f"Webchat script published successfully for app_uuid={dto.app_uuid} at {uploaded_url}"
        )

        return PublishWebchatResult(script_url=uploaded_url)

    def _get_wwc_script_url(self, app_uuid: str) -> str:
        app_data = self._integrations_service.get_channel_app(
            apptype="wwc", app_uuid=app_uuid
        )
        if not app_data:
            raise ValidationError(
                {"app_uuid": "Could not retrieve WWC app from Integrations."}
            )

        script_url = app_data.get("config", {}).get("script")
        if not script_url:
            raise ValidationError(
                {"app_uuid": "WWC app does not have a configured script."}
            )

        return script_url
