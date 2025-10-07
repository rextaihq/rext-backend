"""Unit tests for EmailTemplateService."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.email_template_service import EmailTemplateService
from src.api.models.workspace_models.email_template import EmailTemplate, TemplateType
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextValidationException,
    WrextAuthenticationException,
    ResourceNotFoundException,
)


class FakeScalarSequence:
    """Helper to mimic SQLAlchemy scalar sequence results."""

    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None


class FakeResult:
    """Helper to mimic SQLAlchemy Result objects."""

    def __init__(self, *, scalar=None, scalars=None, rows=None):
        self._scalar = scalar
        self._scalars = scalars or []
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return FakeScalarSequence(self._scalars)

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_get_template_variables_returns_definitions():
    """Should return variables and example usage for known template type."""
    service = EmailTemplateService(db=AsyncMock())

    payload = await service.get_template_variables("workspace_invitation")

    assert payload["template_type"] == "workspace_invitation"
    assert len(payload["available_variables"]) > 0


@pytest.mark.asyncio
async def test_get_template_variables_invalid_type_raises():
    """Unknown template types should raise validation exception."""
    service = EmailTemplateService(db=AsyncMock())

    with pytest.raises(WrextValidationException):
        await service.get_template_variables("unknown_type")


@pytest.mark.asyncio
async def test_preview_template_renders_with_sample_data():
    """preview_template should validate, render, and extract variables."""
    service = EmailTemplateService(db=AsyncMock())

    with patch("src.services.email_template_service.validate_template_variables", return_value=(True, None)) as mock_validate, \
         patch("src.services.email_template_service.get_sample_variables", return_value={"workspace_name": "Acme"}) as mock_sample, \
         patch("src.services.email_template_service.render_template", side_effect=["Rendered Subject", "Rendered Body"]) as mock_render, \
         patch("src.services.email_template_service.extract_variables", return_value=["workspace_name"]) as mock_extract:

        preview = await service.preview_template(
            subject="Welcome to {{workspace_name}}",
            body="Hi {{workspace_name}} team!",
            template_type="workspace_invitation"
        )

    mock_validate.assert_called_once()
    mock_sample.assert_called_once_with("workspace_invitation")
    assert mock_render.call_count == 2
    mock_extract.assert_called_once()

    assert preview["subject"] == "Rendered Subject"
    assert preview["variables_used"] == ["workspace_name"]


@pytest.mark.asyncio
async def test_list_templates_returns_serialized_templates():
    """List templates should verify membership and serialize SQLAlchemy objects."""
    mock_db = AsyncMock()
    service = EmailTemplateService(mock_db)
    workspace_id = uuid4()
    user_id = uuid4()

    template = EmailTemplate(
        workspace_id=workspace_id,
        template_type=TemplateType.WORKSPACE_INVITATION,
        subject="Subject",
        body="Body",
        is_active=True,
        is_default=False,
        created_by_user_id=user_id,
    )

    service._verify_workspace_membership = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalars=[template])

    payload = await service.list_templates(workspace_id, user_id)

    service._verify_workspace_membership.assert_awaited_once()
    assert payload["total_count"] == 1
    assert payload["templates"][0]["template_type"] == "workspace_invitation"


@pytest.mark.asyncio
async def test_list_templates_requires_membership():
    """List templates should surface membership failures."""
    service = EmailTemplateService(db=AsyncMock())
    service._verify_workspace_membership = AsyncMock(side_effect=WrextAuthenticationException("not member"))

    with pytest.raises(WrextAuthenticationException):
        await service.list_templates(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_create_template_success():
    """create_template should validate, persist, and return new template."""
    mock_db = AsyncMock()
    service = EmailTemplateService(mock_db)
    workspace_id = uuid4()
    user_id = uuid4()

    service._verify_workspace_membership = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=None)

    with patch("src.services.email_template_service.validate_template_variables", return_value=(True, None)):
        template = await service.create_template(
            workspace_id=workspace_id,
            user_id=user_id,
            template_type="workspace_invitation",
            subject="Subject",
            body="Body"
        )

    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()
    assert template.workspace_id == workspace_id
    assert template.subject == "Subject"


@pytest.mark.asyncio
async def test_create_template_duplicate_raises():
    """Existing active template should raise DuplicateResourceException."""
    mock_db = AsyncMock()
    service = EmailTemplateService(mock_db)
    workspace_id = uuid4()
    user_id = uuid4()

    service._verify_workspace_membership = AsyncMock()
    existing_template = EmailTemplate(
        workspace_id=workspace_id,
        template_type=TemplateType.WORKSPACE_INVITATION,
        subject="Existing",
        body="Body",
        is_active=True,
    )
    mock_db.execute.return_value = FakeResult(scalar=existing_template)

    with patch("src.services.email_template_service.validate_template_variables", return_value=(True, None)):
        with pytest.raises(DuplicateResourceException):
            await service.create_template(
                workspace_id=workspace_id,
                user_id=user_id,
                template_type="workspace_invitation",
                subject="Subject",
                body="Body"
            )


@pytest.mark.asyncio
async def test_update_template_applies_changes_and_validates():
    """update_template should update fields and validate variables when changed."""
    mock_db = AsyncMock()
    service = EmailTemplateService(mock_db)
    template = EmailTemplate(
        workspace_id=uuid4(),
        template_type=TemplateType.WORKSPACE_INVITATION,
        subject="Old",
        body="Old Body",
        is_active=True,
        created_by_user_id=uuid4(),
    )

    service._get_template_or_404 = AsyncMock(return_value=template)
    service._verify_workspace_membership = AsyncMock()

    with patch("src.services.email_template_service.validate_template_variables", return_value=(True, None)) as mock_validate:
        updated = await service.update_template(
            template_id=uuid4(),
            user_id=uuid4(),
            subject="New",
            body="New Body",
            is_active=False
        )

    mock_validate.assert_called_once()
    mock_db.flush.assert_awaited_once()
    assert updated.subject == "New"
    assert updated.body == "New Body"
    assert updated.is_active is False


@pytest.mark.asyncio
async def test_delete_template_prevents_default_templates():
    """delete_template should raise when attempting to delete default template."""
    mock_db = AsyncMock()
    service = EmailTemplateService(mock_db)
    template = EmailTemplate(
        workspace_id=uuid4(),
        template_type=TemplateType.WORKSPACE_INVITATION,
        subject="Subject",
        body="Body",
        is_default=True,
    )

    service._get_template_or_404 = AsyncMock(return_value=template)
    service._verify_workspace_membership = AsyncMock()

    with pytest.raises(WrextValidationException):
        await service.delete_template(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_get_default_template_returns_defaults():
    """Should return default template from utility helper."""
    service = EmailTemplateService(db=AsyncMock())

    default = await service.get_default_template("workspace_invitation")

    assert default["template_type"] == "workspace_invitation"
    assert "subject" in default


@pytest.mark.asyncio
async def test_get_template_or_404_raises_when_missing():
    """_get_template_or_404 should raise when template does not exist."""
    mock_db = AsyncMock()
    mock_db.execute.return_value = FakeResult(scalar=None)

    service = EmailTemplateService(mock_db)

    with pytest.raises(ResourceNotFoundException):
        await service._get_template_or_404(uuid4())
