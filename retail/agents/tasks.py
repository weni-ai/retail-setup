import logging
from typing import Any, Dict, List, Optional

from celery import shared_task
from django.conf import settings
from django_redis import get_redis_connection

from retail.agents.domains.agent_execution.task_helpers import execution_log_scope
from retail.agents.domains.agent_execution.usecases.cleanup_old_executions import (
    CleanupOldExecutionsUseCase,
)
from retail.agents.domains.agent_execution.usecases.export_agent_logs import (
    ExportAgentLogsDTO,
    ExportAgentLogsUseCase,
)
from retail.agents.domains.agent_execution.usecases.flush_executions import (
    FlushExecutionsUseCase,
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
        return FlushExecutionsUseCase().execute(do_stuck_sweep=do_sweep).as_dict()
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
            f"[DELIVERED_TRACKING] task_started: "
            f"agent_uuid={integrated_agent_uuid} data={webhook_data}"
        )

        webhook_use_case = DeliveredOrderTrackingWebhookUseCase()
        integrated_agent = webhook_use_case.get_integrated_agent(integrated_agent_uuid)
        vtex_account = integrated_agent.project.vtex_account

        result = webhook_use_case.process_webhook_notification(
            integrated_agent, webhook_data
        )

        logger.info(
            f"[DELIVERED_TRACKING] task_completed: "
            f"vtex_account={vtex_account} agent_uuid={integrated_agent_uuid} "
            f"result={result} data={webhook_data}"
        )

    except Exception as e:
        logger.exception(
            f"[DELIVERED_TRACKING] task_failed: "
            f"agent_uuid={integrated_agent_uuid} "
            f"data={webhook_data} error={e}"
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
        dto = ExportAgentLogsDTO.from_task_args(
            agent_uuid=agent_uuid,
            project_uuid=project_uuid,
            search=search,
            date_str=date,
            template_uuids=template_uuids,
            statuses=statuses,
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
    """Process payment recovery webhook notification asynchronously."""
    with execution_log_scope(
        error_data={
            "integrated_agent_uuid": integrated_agent_uuid,
            "webhook_data": webhook_data,
        },
        log_prefix="[PAYMENT_RECOVERY]",
    ) as exec_logger:
        logger.info(
            f"[PAYMENT_RECOVERY] task_started: "
            f"agent_uuid={integrated_agent_uuid} data={webhook_data}"
        )

        use_case = PaymentRecoveryWebhookUseCase()
        # Resolve the agent BEFORE opening any execution log so a missing
        # agent raises NotFound and is caught below without leaving an
        # agentless row behind.
        integrated_agent = use_case.get_integrated_agent(integrated_agent_uuid)

        exec_logger.log_webhook_received(
            integrated_agent=integrated_agent,
            payload=webhook_data,
            order_id=webhook_data.get("OrderId"),
        )
        vtex_account = integrated_agent.project.vtex_account

        result = use_case.process_webhook_notification(integrated_agent, webhook_data)

        logger.info(
            f"[PAYMENT_RECOVERY] task_completed: "
            f"vtex_account={vtex_account} agent_uuid={integrated_agent_uuid} "
            f"result={result} data={webhook_data}"
        )
