"""Use case: drop AgentExecution rows past their retention horizon.

The service ingests thousands of executions per minute, so the table
would grow unbounded without a periodic sweep. The retention horizon
is configured via ``AGENT_EXECUTION_RETENTION_DAYS`` (default 30
days) and is paired with an S3 lifecycle rule on the ``executions/``
prefix that SRE configures separately.

The sweep deletes in bounded batches keyed by primary key. A single
``DELETE WHERE created_on < $1`` against a multi-million-row table
would hold row locks for the full statement duration and is prone
to hitting Postgres ``statement_timeout`` or the Celery soft/hard
timeout — when that happens the task fails silently, the cron
retries on the next schedule, and the table keeps growing. Batching
keeps each statement short-lived; if a single batch fails the
already-deleted batches stay committed and the next run picks up
where this one left off. ``AgentExecution`` has no inbound FKs and
no ``pre_delete``/``post_delete`` receivers, so each batch DELETE
takes Django's fast-delete path (one SQL statement, no PK
round-trip).
"""

import logging
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.utils import timezone

from retail.agents.domains.agent_execution.models import AgentExecution


logger = logging.getLogger(__name__)


class CleanupOldExecutionsUseCase:
    """Delete AgentExecution rows older than the retention horizon."""

    DEFAULT_RETENTION_DAYS = 30
    DEFAULT_BATCH_SIZE = 5000

    def execute(self, retention_days: Optional[int] = None) -> int:
        """Delete rows older than ``retention_days`` and return the count.

        Args:
            retention_days: Override for the retention horizon (in
                days). When ``None``, falls back to
                ``settings.AGENT_EXECUTION_RETENTION_DAYS``, then to
                ``DEFAULT_RETENTION_DAYS``.

        Returns:
            Total number of AgentExecution rows deleted across all
            batches.
        """
        if retention_days is None:
            retention_days = getattr(
                settings,
                "AGENT_EXECUTION_RETENTION_DAYS",
                self.DEFAULT_RETENTION_DAYS,
            )

        batch_size = getattr(
            settings,
            "AGENT_EXECUTION_CLEANUP_BATCH_SIZE",
            self.DEFAULT_BATCH_SIZE,
        )

        cutoff = timezone.now() - timedelta(days=retention_days)
        total_deleted = 0

        while True:
            batch_ids = list(
                AgentExecution.objects.filter(created_on__lt=cutoff).values_list(
                    "pk", flat=True
                )[:batch_size]
            )
            if not batch_ids:
                break
            deleted, _ = AgentExecution.objects.filter(pk__in=batch_ids).delete()
            total_deleted += deleted

        if total_deleted:
            logger.info(
                f"[EXEC_LOG] Cleaned up {total_deleted} agent executions older than "
                f"{retention_days} days"
            )

        return total_deleted
