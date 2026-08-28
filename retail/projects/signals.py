import logging

from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from retail.projects import agentic_cx_tasks
from retail.projects.models import ProjectOnboarding

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=ProjectOnboarding)
def snapshot_previous_completed(sender, instance, **kwargs):
    """
    Stores the previous 'completed' value on the instance so post_save
    can detect the False → True transition. Standard Django pattern for
    field-change detection across pre_save / post_save signals.
    """
    if instance.pk:
        try:
            previous = ProjectOnboarding.all_objects.get(pk=instance.pk)
            instance._previous_completed = previous.completed
        except ProjectOnboarding.DoesNotExist:
            instance._previous_completed = False
    else:
        instance._previous_completed = False


@receiver(post_save, sender=ProjectOnboarding)
def notify_io_on_onboarding_complete(sender, instance, **kwargs):
    """Dispatches task to activate Agentic CX script when onboarding transitions to completed."""
    was_completed = getattr(instance, "_previous_completed", False)

    if not was_completed and instance.completed:
        agentic_cx_tasks.task_ensure_agentic_cx_script_active.delay(
            instance.vtex_account
        )


@receiver(pre_delete, sender=ProjectOnboarding)
def log_onboarding_deletion(sender, instance, **kwargs):
    """Traces unexpected deletions (manual, admin, or CASCADE)."""
    logger.warning(
        f"ProjectOnboarding is being deleted: "
        f"uuid={instance.uuid} vtex_account={instance.vtex_account} "
        f"project={instance.project_id} progress={instance.progress}"
    )
