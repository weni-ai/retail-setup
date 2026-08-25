from celery import shared_task

from retail.projects.usecases.agentic_cx_script import (
    EnsureAgenticCxScriptActiveUseCase,
)


def _run_ensure_agentic_cx_script_active(vtex_account: str) -> None:
    EnsureAgenticCxScriptActiveUseCase().execute(vtex_account)


@shared_task(name="task_ensure_agentic_cx_script_active")
def task_ensure_agentic_cx_script_active(vtex_account: str) -> None:
    """
    Ensures the Agentic CX storefront script is active for the account
    when it is eligible (connected channel, active agent, or completed
    onboarding).
    """
    _run_ensure_agentic_cx_script_active(vtex_account)
