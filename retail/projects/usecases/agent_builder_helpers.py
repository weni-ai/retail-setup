"""
Shared helpers used by the inline and background Agent Builder paths.

The inline path (``ConfigureAgentBuilderUseCase``) and the background
upload path (``UploadNexusContentsUseCase``) both need to:
  1. Load the onboarding record and assert a project is linked.
  2. Idempotently configure the Nexus agent manager.

Extracting these into a single helpers module keeps the "must have a
project" + "configure if missing" contracts in one place and avoids the
two use cases duplicating the logic (or worse, drifting apart).
"""

import logging

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.manager_defaults import (
    MANAGER_PERSONALITY,
    get_manager_defaults,
)
from retail.projects.usecases.onboarding_defaults import get_instructions
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)


class ProjectNotLinkedError(Exception):
    """Raised when Agent Builder configuration is attempted without a linked project."""


def load_onboarding_with_linked_project(vtex_account: str) -> ProjectOnboarding:
    """
    Fetches the onboarding record and asserts it has a linked project.

    Raises:
        ProjectNotLinkedError: If the onboarding has no project linked.
    """
    onboarding = ProjectOnboarding.objects.select_related("project").get(
        vtex_account=vtex_account
    )

    if onboarding.project is None:
        raise ProjectNotLinkedError(
            f"Onboarding {onboarding.uuid} has no project linked yet."
        )

    return onboarding


def ensure_agent_manager_configured(
    project_uuid: str,
    vtex_account: str,
    language: str,
    nexus_service: NexusService,
) -> None:
    """
    Idempotent: configures the agent manager in Nexus if not yet configured.

    Called by both use cases so the upload task can safely run even if
    the inline manager step has not yet completed (e.g. the crawl
    webhook arrived before the inline orchestrator's manager step).
    """
    response = nexus_service.check_agent_builder_exists(project_uuid)

    if response and response.get("data", {}).get("has_agent"):
        logger.info(f"Agent manager already configured for project={project_uuid}")
        return

    defaults = get_manager_defaults(language)

    payload = {
        "agent": {
            "name": f"{vtex_account.title()} Manager",
            "goal": defaults["goal"],
            "role": defaults["role"],
            "personality": MANAGER_PERSONALITY,
        },
        "links": [],
        "instructions": get_instructions(language),
    }

    result = nexus_service.configure_agent_attributes(project_uuid, payload)

    if result is not None:
        logger.info(
            f"Agent manager attributes set for project={project_uuid}: {result}"
        )
    else:
        logger.error(
            f"Failed to set agent manager attributes for project={project_uuid}"
        )
