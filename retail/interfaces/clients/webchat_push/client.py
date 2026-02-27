from typing import Protocol, runtime_checkable


@runtime_checkable
class WebchatPushClientInterface(Protocol):
    def upload_script(self, key: str, script_content: str, redirect_url: str) -> str:
        """Uploads a webchat loader script to S3 with a website redirect header."""
        ...
