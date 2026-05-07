from __future__ import absolute_import

import os

from celery import Celery
from celery.signals import task_postrun, task_prerun

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "retail.settings")

app = Celery("retail", broker_connection_retry_on_startup=True)

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# Celery prefork workers reuse processes across tasks. The agent
# execution UUID lives in a contextvar, so without an explicit reset
# at task boundaries a UUID set by one task could leak into a
# subsequent task running on the same worker process and cause
# traces to be written to the wrong execution. Clearing on both
# task_prerun (defensive: previous task crashed before postrun) and
# task_postrun (normal cleanup) keeps every task starting and ending
# with an empty execution context.
@task_prerun.connect
def clear_execution_context_before_task(*_args, **_kwargs):
    from retail.agents.domains.agent_execution.context import clear_execution_context

    clear_execution_context()


@task_postrun.connect
def clear_execution_context_after_task(*_args, **_kwargs):
    from retail.agents.domains.agent_execution.context import clear_execution_context

    clear_execution_context()
