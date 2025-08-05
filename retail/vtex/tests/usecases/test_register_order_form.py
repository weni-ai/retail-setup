from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4
from rest_framework.exceptions import ValidationError

from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.vtex.dtos.register_order_form_dto import RegisterOrderFormDTO
from retail.vtex.repositories.cart_repository import CartRepository
from retail.vtex.usecases.register_order_form import RegisterOrderFormUseCase


class RegisterOrderFormUseCaseTest(TestCase):
    """Test cases for RegisterOrderFormUseCase."""

    def setUp(self):
        """Set up test fixtures."""
        self.project_uuid = uuid4()
        self.order_form_id = "test_order_form_123"
        self.channel_uuid = uuid4()
        self.cart_uuid = uuid4()

        # Mock DTO
        self.dto = RegisterOrderFormDTO(
            order_form_id=self.order_form_id, channel_uuid=self.channel_uuid
        )

    def test_execute_cart_not_found_creates_new_cart(self):
        """Test executing when cart doesn't exist - should create new cart."""
        # Arrange
        mock_project = MagicMock(spec=Project)
        mock_project.uuid = self.project_uuid

        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        mock_repository = MagicMock(spec=CartRepository)
        mock_repository.find_by_order_form.return_value = None
        mock_repository.create.return_value = mock_cart

        with patch.object(Project.objects, "get", return_value=mock_project):
            usecase = RegisterOrderFormUseCase(
                project_uuid=str(self.project_uuid), repository=mock_repository
            )

            # Act
            result = usecase.execute(self.dto)

            # Assert
            self.assertEqual(result, mock_cart)
            mock_repository.find_by_order_form.assert_called_once_with(
                self.order_form_id, mock_project
            )
            mock_repository.create.assert_called_once_with(
                order_form_id=self.order_form_id,
                project=mock_project,
                flows_channel_uuid=self.channel_uuid,
            )

    def test_execute_cart_found_returns_existing_cart(self):
        """Test executing when cart exists - should return existing cart."""
        # Arrange
        mock_project = MagicMock(spec=Project)
        mock_project.uuid = self.project_uuid

        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        mock_repository = MagicMock(spec=CartRepository)
        mock_repository.find_by_order_form.return_value = mock_cart

        with patch.object(Project.objects, "get", return_value=mock_project):
            usecase = RegisterOrderFormUseCase(
                project_uuid=str(self.project_uuid), repository=mock_repository
            )

            # Act
            result = usecase.execute(self.dto)

            # Assert
            self.assertEqual(result, mock_cart)
            mock_repository.find_by_order_form.assert_called_once_with(
                self.order_form_id, mock_project
            )
            mock_repository.create.assert_not_called()

    def test_execute_project_not_found_raises_validation_error(self):
        """Test executing when project doesn't exist - should raise ValidationError."""
        # Arrange
        mock_repository = MagicMock(spec=CartRepository)

        with patch.object(Project.objects, "get", side_effect=Project.DoesNotExist):
            usecase = RegisterOrderFormUseCase(
                project_uuid=str(self.project_uuid), repository=mock_repository
            )

            # Act & Assert
            with self.assertRaises(ValidationError) as context:
                usecase.execute(self.dto)

            self.assertIn(
                f"Project with UUID '{self.project_uuid}' not found",
                str(context.exception),
            )

    def test_execute_duplicate_projects_raises_validation_error(self):
        """Test executing when duplicate projects exist - should raise ValidationError."""
        # Arrange
        mock_repository = MagicMock(spec=CartRepository)

        with patch.object(
            Project.objects, "get", side_effect=Project.MultipleObjectsReturned
        ):
            usecase = RegisterOrderFormUseCase(
                project_uuid=str(self.project_uuid), repository=mock_repository
            )

            # Act & Assert
            with self.assertRaises(ValidationError) as context:
                usecase.execute(self.dto)

            self.assertIn(
                f"Duplicate projects found with UUID '{self.project_uuid}'",
                str(context.exception),
            )

    def test_execute_with_different_order_form_id(self):
        """Test executing with different order_form_id."""
        # Arrange
        different_order_form_id = "different_order_form_456"
        different_dto = RegisterOrderFormDTO(
            order_form_id=different_order_form_id, channel_uuid=self.channel_uuid
        )

        mock_project = MagicMock(spec=Project)
        mock_project.uuid = self.project_uuid

        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        mock_repository = MagicMock(spec=CartRepository)
        mock_repository.find_by_order_form.return_value = None
        mock_repository.create.return_value = mock_cart

        with patch.object(Project.objects, "get", return_value=mock_project):
            usecase = RegisterOrderFormUseCase(
                project_uuid=str(self.project_uuid), repository=mock_repository
            )

            # Act
            result = usecase.execute(different_dto)

            # Assert
            self.assertEqual(result, mock_cart)
            mock_repository.find_by_order_form.assert_called_once_with(
                different_order_form_id, mock_project
            )
            mock_repository.create.assert_called_once_with(
                order_form_id=different_order_form_id,
                project=mock_project,
                flows_channel_uuid=self.channel_uuid,
            )

    def test_execute_with_different_channel_uuid(self):
        """Test executing with different channel_uuid."""
        # Arrange
        different_channel_uuid = uuid4()
        different_dto = RegisterOrderFormDTO(
            order_form_id=self.order_form_id, channel_uuid=different_channel_uuid
        )

        mock_project = MagicMock(spec=Project)
        mock_project.uuid = self.project_uuid

        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        mock_repository = MagicMock(spec=CartRepository)
        mock_repository.find_by_order_form.return_value = None
        mock_repository.create.return_value = mock_cart

        with patch.object(Project.objects, "get", return_value=mock_project):
            usecase = RegisterOrderFormUseCase(
                project_uuid=str(self.project_uuid), repository=mock_repository
            )

            # Act
            result = usecase.execute(different_dto)

            # Assert
            self.assertEqual(result, mock_cart)
            mock_repository.find_by_order_form.assert_called_once_with(
                self.order_form_id, mock_project
            )
            mock_repository.create.assert_called_once_with(
                order_form_id=self.order_form_id,
                project=mock_project,
                flows_channel_uuid=different_channel_uuid,
            )

    def test_execute_with_different_project_uuid(self):
        """Test executing with different project_uuid."""
        # Arrange
        different_project_uuid = uuid4()
        different_mock_project = MagicMock(spec=Project)
        different_mock_project.uuid = different_project_uuid

        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        mock_repository = MagicMock(spec=CartRepository)
        mock_repository.find_by_order_form.return_value = None
        mock_repository.create.return_value = mock_cart

        with patch.object(Project.objects, "get", return_value=different_mock_project):
            usecase = RegisterOrderFormUseCase(
                project_uuid=str(different_project_uuid), repository=mock_repository
            )

            # Act
            result = usecase.execute(self.dto)

            # Assert
            self.assertEqual(result, mock_cart)
            mock_repository.find_by_order_form.assert_called_once_with(
                self.order_form_id, different_mock_project
            )
            mock_repository.create.assert_called_once_with(
                order_form_id=self.order_form_id,
                project=different_mock_project,
                flows_channel_uuid=self.channel_uuid,
            )

    def test_execute_idempotent_behavior(self):
        """Test that the operation is idempotent - multiple calls return same cart."""
        # Arrange
        mock_project = MagicMock(spec=Project)
        mock_project.uuid = self.project_uuid

        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        mock_repository = MagicMock(spec=CartRepository)
        mock_repository.find_by_order_form.return_value = mock_cart

        with patch.object(Project.objects, "get", return_value=mock_project):
            usecase = RegisterOrderFormUseCase(
                project_uuid=str(self.project_uuid), repository=mock_repository
            )

            # Act - Execute multiple times
            result1 = usecase.execute(self.dto)
            result2 = usecase.execute(self.dto)
            result3 = usecase.execute(self.dto)

            # Assert
            self.assertEqual(result1, mock_cart)
            self.assertEqual(result2, mock_cart)
            self.assertEqual(result3, mock_cart)

            # Should only call find_by_order_form, never create
            self.assertEqual(mock_repository.find_by_order_form.call_count, 3)
            mock_repository.create.assert_not_called()

    def test_execute_with_empty_order_form_id(self):
        """Test executing with empty order_form_id."""
        # Arrange
        empty_order_form_id = ""
        empty_dto = RegisterOrderFormDTO(
            order_form_id=empty_order_form_id, channel_uuid=self.channel_uuid
        )

        mock_project = MagicMock(spec=Project)
        mock_project.uuid = self.project_uuid

        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        mock_repository = MagicMock(spec=CartRepository)
        mock_repository.find_by_order_form.return_value = None
        mock_repository.create.return_value = mock_cart

        with patch.object(Project.objects, "get", return_value=mock_project):
            usecase = RegisterOrderFormUseCase(
                project_uuid=str(self.project_uuid), repository=mock_repository
            )

            # Act
            result = usecase.execute(empty_dto)

            # Assert
            self.assertEqual(result, mock_cart)
            mock_repository.find_by_order_form.assert_called_once_with(
                empty_order_form_id, mock_project
            )
            mock_repository.create.assert_called_once_with(
                order_form_id=empty_order_form_id,
                project=mock_project,
                flows_channel_uuid=self.channel_uuid,
            )

    def test_execute_with_none_order_form_id(self):
        """Test executing with None order_form_id."""
        # Arrange
        none_order_form_id = None
        none_dto = RegisterOrderFormDTO(
            order_form_id=none_order_form_id, channel_uuid=self.channel_uuid
        )

        mock_project = MagicMock(spec=Project)
        mock_project.uuid = self.project_uuid

        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        mock_repository = MagicMock(spec=CartRepository)
        mock_repository.find_by_order_form.return_value = None
        mock_repository.create.return_value = mock_cart

        with patch.object(Project.objects, "get", return_value=mock_project):
            usecase = RegisterOrderFormUseCase(
                project_uuid=str(self.project_uuid), repository=mock_repository
            )

            # Act
            result = usecase.execute(none_dto)

            # Assert
            self.assertEqual(result, mock_cart)
            mock_repository.find_by_order_form.assert_called_once_with(
                none_order_form_id, mock_project
            )
            mock_repository.create.assert_called_once_with(
                order_form_id=none_order_form_id,
                project=mock_project,
                flows_channel_uuid=self.channel_uuid,
            )

    def test_init_without_repository_uses_default(self):
        """Test initialization without repository uses default CartRepository."""
        # Arrange & Act
        usecase = RegisterOrderFormUseCase(project_uuid=str(self.project_uuid))

        # Assert
        self.assertIsInstance(usecase._repo, CartRepository)
        self.assertEqual(usecase._project_uuid, str(self.project_uuid))

    def test_init_with_custom_repository(self):
        """Test initialization with custom repository."""
        # Arrange
        custom_repository = MagicMock(spec=CartRepository)

        # Act
        usecase = RegisterOrderFormUseCase(
            project_uuid=str(self.project_uuid), repository=custom_repository
        )

        # Assert
        self.assertEqual(usecase._repo, custom_repository)
        self.assertEqual(usecase._project_uuid, str(self.project_uuid))
