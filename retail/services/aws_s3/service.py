from typing import BinaryIO, Optional

from django.core.files.uploadedfile import UploadedFile

from retail.interfaces.clients.aws_s3.client import S3ClientInterface
from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.clients.aws_s3.client import S3Client

from retail.services.aws_s3.converters import Base64ToUploadedFileConverter


class S3Service(S3ServiceInterface):
    def __init__(
        self,
        client: Optional[S3ClientInterface] = None,
        bucket_name: Optional[str] = None,
    ):
        # When the caller doesn't inject a client, build one bound to
        # ``bucket_name`` so the same service class can serve different
        # storage namespaces (e.g. user uploads vs. execution traces)
        # without anyone having to subclass or monkey-patch boto3.
        self.client = client or S3Client(bucket_name=bucket_name)
        self.base_64_converter = Base64ToUploadedFileConverter()

    def upload_file(self, file: UploadedFile, key: str) -> str:
        """Uploads a file to an S3 bucket and returns the key."""
        return self.client.upload_file(file, key)

    def upload_fileobj(
        self,
        fileobj: BinaryIO,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Streams a binary file-like object to S3 (multipart-capable)."""
        return self.client.upload_fileobj(fileobj, key, content_type)

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """Generates a presigned URL for accessing a private S3 object."""
        return self.client.generate_presigned_url(key, expiration)

    def get_object(self, key: str) -> Optional[bytes]:
        """Downloads object content from S3.

        Args:
            key: The S3 object key.

        Returns:
            The object content as bytes, or None if the object doesn't exist.
        """
        return self.client.get_object(key)

    def put_object(
        self, key: str, content: bytes, content_type: str = "application/json"
    ) -> str:
        """Uploads raw content to S3.

        Args:
            key: The S3 object key.
            content: The content to upload as bytes.
            content_type: The MIME type of the content.

        Returns:
            The S3 key of the uploaded object.
        """
        return self.client.put_object(key, content, content_type)
