from typing import BinaryIO, Optional, Protocol, runtime_checkable

from django.core.files.uploadedfile import UploadedFile


@runtime_checkable
class S3ClientInterface(Protocol):
    def upload_file(self, file: UploadedFile, key: str) -> str:
        """Uploads a file to an S3 bucket."""
        pass

    def upload_fileobj(
        self,
        fileobj: BinaryIO,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Streams a binary file-like object to S3.

        Unlike ``put_object`` (which takes the full payload in memory),
        this reads ``fileobj`` incrementally and lets boto3 switch to a
        multipart upload for large streams.

        Args:
            fileobj: A readable binary file-like object positioned at the
                start of the content to upload.
            key: The S3 object key.
            content_type: The MIME type of the content.

        Returns:
            The S3 key of the uploaded object.
        """
        pass

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """Generates a presigned URL for accessing a private S3 object."""
        pass

    def get_object(self, key: str) -> Optional[bytes]:
        """Downloads object content from S3.

        Args:
            key: The S3 object key.

        Returns:
            The object content as bytes, or None if the object doesn't exist.
        """
        pass

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
        pass
