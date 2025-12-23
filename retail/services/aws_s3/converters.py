import base64
import logging
from uuid import uuid4
from io import BytesIO
from typing import Protocol, Any, Optional, runtime_checkable

import requests
from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile


logger = logging.getLogger(__name__)


@runtime_checkable
class ConverterInterface(Protocol):
    def convert(self, file: Any) -> UploadedFile:
        pass


class ImageUrlToBase64Converter:
    """Converts an image URL to a base64 Data URI string."""

    IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
    DEFAULT_CONTENT_TYPE = "image/png"
    REQUEST_TIMEOUT = 30

    def is_image_url(self, url: str) -> bool:
        """Check if the string is an image URL."""
        if not url or not isinstance(url, str):
            return False
        if not url.startswith(("http://", "https://")):
            return False
        url_without_query = url.split("?")[0]
        return url_without_query.lower().endswith(self.IMAGE_EXTENSIONS)

    def convert(self, image_url: str) -> Optional[str]:
        """
        Download image from URL and convert to base64 Data URI.

        Args:
            image_url: The URL of the image to convert.

        Returns:
            Base64 Data URI string (data:{mime};base64,{content}) or None if conversion fails.
        """
        if not self.is_image_url(image_url):
            return None

        try:
            response = requests.get(image_url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type", self.DEFAULT_CONTENT_TYPE
            )
            # Clean content-type (remove charset if present)
            if ";" in content_type:
                content_type = content_type.split(";")[0].strip()

            image_base64 = base64.b64encode(response.content).decode("utf-8")
            return f"data:{content_type};base64,{image_base64}"

        except requests.RequestException as e:
            logger.error(f"Failed to download image from URL {image_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to convert image URL to base64: {e}")
            return None


class Base64ToUploadedFileConverter(ConverterInterface):
    def convert(self, file: str) -> UploadedFile:
        """
        Converts a base64 encoded string to an UploadedFile. The string should be in the format:
        data:[<content_type>];base64,<base64_data>
        """
        if "," in file:
            header, base64_data = file.split(",", 1)
        else:
            base64_data = file
            header = ""

        file_data = base64.b64decode(base64_data)

        extension = "jpg"
        content_type = "image/jpeg"

        if header.startswith("data:") and ";base64" in header:
            content_type_from_header = header.split("data:")[1].split(";base64")[0]
            if "/" in content_type_from_header:
                type_main, type_ext = content_type_from_header.split("/", 1)
                if type_main == "image":
                    content_type = f"{type_main}/{type_ext}"
                    extension = type_ext

        filename = f"{uuid4().hex}.{extension}"

        file_io = BytesIO(file_data)
        file_size = file_io.getbuffer().nbytes

        return InMemoryUploadedFile(
            file=file_io,
            field_name=None,
            name=filename,
            content_type=content_type,
            size=file_size,
            charset=None,
        )
