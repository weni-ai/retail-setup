from typing import Protocol


class SlackClientInterface(Protocol):
    def send_blocks(self, channel: str, blocks: list) -> bool:
        ...
