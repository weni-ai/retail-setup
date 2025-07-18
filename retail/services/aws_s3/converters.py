import base64
from uuid import uuid4
from io import BytesIO
from typing import Protocol, Any, runtime_checkable
from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile


@runtime_checkable
class ConverterInterface(Protocol):
    def convert(self, file: Any) -> UploadedFile:
        pass


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
