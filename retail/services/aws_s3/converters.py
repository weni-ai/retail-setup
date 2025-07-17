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

        content_type = None
        extension = ""

        if header.startswith("data:") and ";base64" in header:
            content_type = header.split("data:")[1].split(";base64")[0]
            if "/" in content_type:
                extension = content_type.split("/")[1]

        prefix_name = str(uuid4().hex)
        filename = f"{prefix_name}.{extension}" if extension else prefix_name

        file_io = BytesIO(file_data)
        file_size = file_io.getbuffer().nbytes

        uploaded_file = InMemoryUploadedFile(
            file=file_io,
            field_name=None,
            name=filename,
            content_type=content_type,
            size=file_size,
            charset=None,
        )

        return uploaded_file
