import copy

from typing import List, Optional, Dict, Any

from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.services.aws_s3.service import S3Service


class TemplateMetadataHandler:
    def __init__(self, s3_service: Optional[S3ServiceInterface] = None):
        self.s3_service = s3_service or S3Service()

    def _upload_header_image(self, header: Dict[str, Any]) -> str:
        """Upload header image to S3 and return the unique file key."""
        file = self.s3_service.base_64_converter.convert(header.get("text"))
        key = f"template_headers/{file.name}"
        uploaded_key = self.s3_service.upload_file(file, key=key)
        return uploaded_key

    def build_metadata(
        self, translation: Dict[str, Any], category: Optional[str] = None
    ) -> dict:
        return {
            "body": translation.get("template_body"),
            "body_params": translation.get("template_body_params"),
            "header": translation.get("template_header"),
            "footer": translation.get("template_footer"),
            "buttons": translation.get("template_button"),
            "category": category or translation.get("category"),
        }

    def post_process_translation(
        self, metadata: Dict[str, Any], translation_payload: Dict[str, Any]
    ) -> dict:
        metadata = copy.deepcopy(metadata)
        translation_payload_copy = copy.deepcopy(translation_payload)

        if "buttons" in translation_payload_copy:
            metadata["buttons"] = translation_payload_copy["buttons"]
        if "header" in translation_payload_copy:
            metadata["header"] = translation_payload_copy["header"]
            if (
                "header_type" in translation_payload_copy["header"]
                and translation_payload_copy["header"]["header_type"] == "IMAGE"
            ):
                header_text = translation_payload_copy["header"].get("text", "")
                # Skip upload if already a URL (http/https) - used for placeholder images
                if not header_text.startswith(("http://", "https://")):
                    metadata["header"]["text"] = self._upload_header_image(
                        translation_payload_copy["header"]
                    )

        return metadata

    def extract_start_condition(self, parameters: List[Dict[str, Any]], default=None):
        return next(
            (p.get("value") for p in parameters if p.get("name") == "start_condition"),
            default,
        )

    def extract_variables(
        self, parameters: List[Dict[str, Any]], default=None
    ) -> List[Dict[str, Any]]:
        return next(
            (
                param.get("value")
                for param in parameters
                if param.get("name") == "variables"
            ),
            default,
        )
