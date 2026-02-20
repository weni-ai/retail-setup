from dataclasses import dataclass, field


@dataclass(frozen=True)
class CrawlerWebhookDTO:
    """Data received from the crawler webhook event."""

    task_id: str
    event: str
    timestamp: str
    url: str
    progress: int = 0
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class StartOnboardingDTO:
    """Data sent by the front-end to start the onboarding process."""

    vtex_account: str
    crawl_url: str
