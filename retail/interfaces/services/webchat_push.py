from typing import Protocol


class WebchatPushServiceInterface(Protocol):
    def publish_webchat_script(self, script_url: str, account_id: str) -> str:
        """Builds the webchat loader script and uploads it to the push-webchat bucket."""
        ...
