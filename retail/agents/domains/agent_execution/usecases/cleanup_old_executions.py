"""Use case: drop AgentExecution rows past their retention horizon.

The service ingests thousands of executions per minute, so the table
would grow unbounded without a periodic sweep. The retention horizon
is configured via ``AGENT_EXECUTION_RETENTION_DAYS`` (default 30
days) and is paired with an S3 lifecycle rule on the ``executions/``
prefix that SRE configures separately.
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

    def execute(self, retention_days: Optional[int] = None) -> int:
        """Delete rows older than ``retention_days`` and return the count.

        Args:
            retention_days: Override for the retention horizon (in
                days). When ``None``, falls back to
                ``settings.AGENT_EXECUTION_RETENTION_DAYS``, then to
                ``DEFAULT_RETENTION_DAYS``.

        Returns:
            Number of AgentExecution rows deleted.
        """
        if retention_days is None:
            retention_days = getattr(
                settings,
                "AGENT_EXECUTION_RETENTION_DAYS",
                self.DEFAULT_RETENTION_DAYS,
            )

        cutoff = timezone.now() - timedelta(days=retention_days)
        deleted, _ = AgentExecution.objects.filter(created_on__lt=cutoff).delete()

        if deleted:
            logger.info(
                f"[EXEC_LOG] Cleaned up {deleted} agent executions older than "
                f"{retention_days} days"
            )

        return deleted
