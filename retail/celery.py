from __future__ import absolute_import

import os

from celery import Celery
from celery.signals import task_postrun, task_prerun

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "retail.settings")

app = Celery("retail", broker_connection_retry_on_startup=True)

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


def _reset_execution_context(*_args, **_kwargs) -> None:
    """Clear the agent execution contextvar at Celery task boundaries.

    Celery prefork workers reuse processes across tasks, so without
    an explicit reset the execution UUID set by one task could leak
    into a subsequent task running on the same worker process and
    cause traces to be written to the wrong execution. We hook both
    ``task_prerun`` (defensive — in case the previous task crashed
    before ``task_postrun``) and ``task_postrun`` (normal cleanup)
    so every task starts and ends with an empty execution context.
    """
    from retail.agents.domains.agent_execution.context import clear_execution_context

    clear_execution_context()


task_prerun.connect(_reset_execution_context)
task_postrun.connect(_reset_execution_context)
