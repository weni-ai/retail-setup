from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from retail.broadcasts.models import ProjectBroadcastCounter
from retail.projects.models import Project


class ProjectBroadcastCounterReprTest(TestCase):
    """Covers the two branches of __str__ used by Django admin and logs."""

    def setUp(self):
        self.project = Project.objects.create(name="Project A", uuid=uuid4())

    def test_repr_when_not_blocked(self):
        counter = ProjectBroadcastCounter.objects.create(
            project=self.project, total_delivered=42
        )
        text = str(counter)

        self.assertIn(str(self.project.uuid), text)
        self.assertIn("total_delivered=42", text)
        self.assertIn("blocked=False", text)

    def test_repr_when_blocked(self):
        counter = ProjectBroadcastCounter.objects.create(
            project=self.project,
            total_delivered=100,
            blocked_at=timezone.now(),
        )
        text = str(counter)

        self.assertIn(str(self.project.uuid), text)
        self.assertIn("total_delivered=100", text)
        self.assertIn("blocked_at=", text)
        self.assertNotIn("blocked=False", text)
