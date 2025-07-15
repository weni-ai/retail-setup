from typing import List, Optional, Dict, Any

from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.services.aws_s3.service import S3Service


class TemplateMetadataHandler:
    def __init__(self, s3_service: Optional[S3ServiceInterface] = None):
        self.s3_service = s3_service or S3Service()

    def _upload_header_image(self, header: Dict[str, Any]) -> str:
        file = self.s3_service.base_64_converter.convert(header.get("text"))
        url = self.s3_service.upload_file(file, key=f"template_headers/{file.name}")
        return url

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
        metadata = dict(metadata)
        if "buttons" in translation_payload:
            metadata["buttons"] = translation_payload["buttons"]
        if "header" in translation_payload:
            metadata["header"] = translation_payload["header"]
            metadata["header"]["text"] = self._upload_header_image(
                translation_payload["header"]
            )

        return metadata

    def extract_start_condition(self, parameters: List[Dict[str, Any]], default=None):
        return next(
            (p.get("value") for p in parameters if p.get("name") == "start_condition"),
            default,
        )
