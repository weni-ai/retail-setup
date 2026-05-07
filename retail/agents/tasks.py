import logging
from datetime import date as date_type
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task
from django.conf import settings
from django_redis import get_redis_connection

from retail.agents.domains.agent_execution.services.buffer import ExecutionBufferService
from retail.agents.domains.agent_execution.services.logger import ExecutionLoggerService
from retail.agents.domains.agent_execution.usecases.cleanup_old_executions import (
    CleanupOldExecutionsUseCase,
)
from retail.agents.domains.agent_execution.usecases.export_agent_logs import (
    ExportAgentLogsFilter,
    ExportAgentLogsUseCase,
)
from retail.agents.domains.agent_integration.usecases.delivered_order_tracking import (
    DeliveredOrderTrackingWebhookUseCase,
)
from retail.agents.domains.agent_integration.usecases.payment_recovery import (
    PaymentRecoveryWebhookUseCase,
)


logger = logging.getLogger(__name__)


_FLUSH_TICK_KEY = "agent_execution:flush_tick"


def _next_flush_tick() -> int:
    """Atomically increment a shared counter so only every Nth tick sweeps.

    Using Redis ``INCR`` directly keeps the counter coherent across
    multiple workers running the flush task in parallel. ``INCR``
    creates the key with value ``0`` and returns ``1`` on first call,
    so the very first task run is treated as tick 1. A failure here
    must not block the flush itself, so we fall back to ``0`` (no
    sweep this tick) and let the next tick try again.
    """
    try:
        return int(get_redis_connection("default").incr(_FLUSH_TICK_KEY))
    except Exception:
        logger.warning(
            "[EXEC_LOG] Could not increment flush tick counter; "
            "skipping stuck sweep this tick",
            exc_info=True,
        )
        return 0


@shared_task(name="task_flush_execution_logs")
def task_flush_execution_logs() -> Dict[str, int]:
    """Drain the agent-execution flush queue and persist to DB + S3.

    Beat schedules this every ``AGENT_EXECUTION_FLUSH_INTERVAL_SECONDS``.
    Every Nth tick (controlled by
    ``AGENT_EXECUTION_STUCK_SWEEP_EVERY_N_TICKS``) the same task also
    runs the SQL sweep that finalises rows still ``processing`` past
    the stuck threshold — covers cases where Redis lost the ZSET
    entry but the DB row is still in-flight.

    Returns ``{"flushed": int, "stuck_finalized": int}``. Errors are
    swallowed so the periodic schedule keeps trying without raising.
    """
    try:
        sweep_every = max(
            1, int(getattr(settings, "AGENT_EXECUTION_STUCK_SWEEP_EVERY_N_TICKS", 60))
        )
        tick = _next_flush_tick()
        do_sweep = tick > 0 and (tick % sweep_every) == 0
        return ExecutionBufferService().flush(do_stuck_sweep=do_sweep)
    except Exception:
        logger.exception("[EXEC_LOG] Error flushing agent execution logs")
        return {"flushed": 0, "stuck_finalized": 0}


@shared_task(name="task_cleanup_old_executions")
def task_cleanup_old_executions() -> int:
    """Periodic glue around CleanupOldExecutionsUseCase.

    Returns the number of rows deleted, or 0 on failure so the beat
    schedule keeps trying without raising.
    """
    try:
        return CleanupOldExecutionsUseCase().execute()
    except Exception:
        logger.exception("[EXEC_LOG] Error cleaning up old agent executions")
        return 0


@shared_task
def task_delivered_order_tracking_webhook(
    integrated_agent_uuid: str, webhook_data: Dict[str, Any]
) -> None:
    """
    Process delivered order tracking webhook notification asynchronously.

    Args:
        integrated_agent_uuid: UUID of the integrated agent
        webhook_data: Data received from VTEX webhook
    """
    try:
        logger.info(
            f"Processing delivered order tracking webhook task for agent {integrated_agent_uuid}"
        )

        webhook_use_case = DeliveredOrderTrackingWebhookUseCase()

        integrated_agent = webhook_use_case.get_integrated_agent(integrated_agent_uuid)

        result = webhook_use_case.process_webhook_notification(
            integrated_agent, webhook_data
        )

        logger.info(
            f"Successfully processed delivered order tracking webhook for agent {integrated_agent_uuid}: {result}"
        )

    except Exception as e:
        logger.exception(
            f"Error processing delivered order tracking webhook task for agent {integrated_agent_uuid}: {e}"
        )


@shared_task(name="task_export_agent_logs")
def task_export_agent_logs(
    agent_uuid: str,
    project_uuid: str,
    search: Optional[str] = None,
    date: Optional[str] = None,
    template_uuids: Optional[List[str]] = None,
    statuses: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Build the agent-logs CSV export and stash it on S3.

    Fire-and-forget: the caller treats any non-error status as success
    and we deliver the file out-of-band. This iteration only persists
    the CSV + presigned URL and logs them — wiring an email /
    notification channel is a separate piece of work.

    Args:
        agent_uuid: ``IntegratedAgent.uuid`` to scope the export to.
        project_uuid: Tenant guard from the ``Project-Uuid`` header.
        search: Optional ILIKE filter applied to contact/order_id.
        date: Optional ``YYYY-MM-DD`` calendar day (UTC).
        template_uuids: Optional template-UUID OR filter.
        statuses: Optional log-status OR filter (skipped/sent/...).

    Returns:
        The presigned S3 URL on success, or ``None`` on failure.
        Errors are logged so a failed export never crashes the
        worker.
    """
    try:
        parsed_date: Optional[date_type] = None
        if date:
            parsed_date = date_type.fromisoformat(date)

        dto = ExportAgentLogsFilter(
            agent_uuid=UUID(agent_uuid),
            project_uuid=UUID(project_uuid),
            search=search,
            date=parsed_date,
            template_uuids=tuple(UUID(t) for t in (template_uuids or [])),
            statuses=tuple(statuses or ()),
        )
        _, presigned_url = ExportAgentLogsUseCase().execute(dto)

        logger.info(
            "[AGENT_LOGS_EXPORT] CSV ready for agent=%s project=%s url=%s",
            agent_uuid,
            project_uuid,
            presigned_url,
        )
        return presigned_url
    except Exception:
        logger.exception(
            "[AGENT_LOGS_EXPORT] Failed to build CSV for agent=%s project=%s",
            agent_uuid,
            project_uuid,
        )
        return None


@shared_task
def task_payment_recovery_webhook(
    integrated_agent_uuid: str, webhook_data: Dict[str, Any]
) -> None:
    """
    Process payment recovery webhook notification asynchronously.

    Args:
        integrated_agent_uuid: UUID of the integrated agent
        webhook_data: Data received from VTEX webhook
    """
    execution_uuid: Optional[UUID] = None
    exec_logger = ExecutionLoggerService()

    try:
        logger.info(f"[PaymentRecovery] Task started - agent={integrated_agent_uuid}")

        use_case = PaymentRecoveryWebhookUseCase()
        # Resolve the agent BEFORE opening any execution log so a missing
        # agent raises NotFound and is caught below without leaving an
        # agentless row behind
        integrated_agent = use_case.get_integrated_agent(integrated_agent_uuid)

        execution_uuid = exec_logger.log_webhook_received(
            integrated_agent=integrated_agent,
            payload=webhook_data,
            order_id=webhook_data.get("OrderId"),
        )

        result = use_case.process_webhook_notification(integrated_agent, webhook_data)

        logger.info(
            f"[PaymentRecovery] Task completed successfully - "
            f"agent={integrated_agent_uuid} result={result}"
        )

    except Exception as e:
        if execution_uuid:
            exec_logger.log_execution_error(
                execution_uuid=execution_uuid,
                error_message=str(e),
                error_data={"webhook_data": webhook_data},
            )
        logger.exception(
            f"[PaymentRecovery] Task failed - agent={integrated_agent_uuid}: {e}"
        )
