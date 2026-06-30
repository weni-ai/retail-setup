"""
Shared helpers for background content-base crawl and upload progress.

Used by ``UpdateOnboardingProgressUseCase``, ``UploadNexusContentsUseCase``,
``GetContentBaseProgressUseCase``, and the Nexus upload Celery task to persist
and compute progress under ``config["content_base_progress"]``.
"""

from retail.projects.models import ProjectOnboarding

CRAWL_WEIGHT = 33
UPLOAD_WEIGHT = 67

STATUS_PENDING = "pending"
STATUS_CRAWLING = "crawling"
STATUS_UPLOADING = "uploading"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


def compute_overall_percent(snapshot: dict) -> int:
    if not snapshot:
        return 0
    if snapshot.get("status") == STATUS_COMPLETE:
        return 100
    crawl = snapshot.get("crawl_percent", 0)
    upload = snapshot.get("upload_percent", 0)
    return min(100, round(crawl * CRAWL_WEIGHT / 100 + upload * UPLOAD_WEIGHT / 100))


def compute_upload_percent(
    batch_index: int,
    batch_size: int,
    total_files: int,
    batch_progress_pct: int,
    *,
    batch_max_files: int = 25,
) -> int:
    if total_files <= 0:
        return 0
    files_before_batch = batch_index * batch_max_files
    return min(
        100,
        round(
            (files_before_batch + batch_progress_pct * batch_size / 100)
            / total_files
            * 100
        ),
    )


def persist_content_base_progress(onboarding: ProjectOnboarding, **updates) -> None:
    config = onboarding.config or {}
    snapshot = dict(config.get("content_base_progress") or {})
    snapshot.update(updates)
    config["content_base_progress"] = snapshot
    onboarding.config = config
    onboarding.save(update_fields=["config"])
