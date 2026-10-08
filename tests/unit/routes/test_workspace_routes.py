from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.api.security.dependencies import get_current_user
from src.api.server import app


@pytest.mark.asyncio
async def test_create_workspace_returns_operation_id(client) -> None:
    """
    Ensure the workspace creation route surfaces both workspace data and
    operation_id so callers can initiate SSE subscriptions.
    """
    user_identity = uuid4()

    def override_current_user():
        return {"identity": str(user_identity)}

    app.dependency_overrides[get_current_user] = override_current_user

    expected_payload = {
        # The route runs UUID() on this id for its audit-log entry, so it must
        # be a well-formed UUID string.
        "workspace": {"id": str(uuid4()), "name": "Example Workspace"},
        "operation_id": "op-abc-123",
    }

    try:
        # The audit-log write is a side effect, not the behaviour under test;
        # stubbed because the override user does not exist as a row (FK).
        with (
            patch("src.api.routes.workspaces.workspace_core.WorkspaceService") as mock_service_cls,
            patch(
                "src.utils.audit_helper.create_audit_log_async",
                new=AsyncMock(return_value=None),
            ),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.create_workspace_for_user = AsyncMock(return_value=expected_payload)

            response = await client.post(
                "/api/v1/workspaces/",
                json={
                    "name": "Example Workspace",
                    "description": "A workspace for testing",
                    "url": "https://example.com",
                },
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    body = response.json()

    assert body["success"] is True
    assert body["data"]["workspace"] == expected_payload["workspace"]
    assert body["data"]["operation_id"] == expected_payload["operation_id"]
    assert "Background processing initiated" in body["message"]
    mock_service.create_workspace_for_user.assert_awaited_once()


# A workspace for a business with no website yet (revnix/rext-control#853): the request carries
# the owner's description in place of an address.

DESCRIPTION = "We bake sourdough bread and pastries for cafés and restaurants in Leeds."


async def _create(client, body):
    """POST the create request as a signed-in user, with the service and the reachability check
    replaced. Returns the response, the service's create and the check."""
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(uuid4())}
    created = {"workspace": {"id": str(uuid4()), "name": body.get("name")}, "operation_id": "op-1"}
    try:
        with (
            patch("src.api.routes.workspaces.workspace_core.WorkspaceService") as service_cls,
            patch(
                "src.api.routes.workspaces.workspace_core.check_website_reachable",
                # The check answers with the address to keep: here, the one it was asked about.
                new=AsyncMock(side_effect=lambda url: url),
            ) as reachable,
            patch("src.utils.audit_helper.create_audit_log_async", new=AsyncMock()),
        ):
            create = service_cls.return_value.create_workspace_for_user = AsyncMock(
                return_value=created
            )
            response = await client.post("/api/v1/workspaces/", json=body)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    return response, create, reachable


@pytest.mark.asyncio
async def test_create_takes_a_description_when_there_is_no_website(client) -> None:
    response, create, reachable = await _create(
        client, {"name": "Crumb and Crust", "description": f"  {DESCRIPTION} "}
    )

    assert response.status_code == 201
    assert response.json()["data"]["operation_id"] == "op-1"
    sent = create.await_args.kwargs
    assert sent["url"] is None
    assert sent["description"] == DESCRIPTION
    # No address, so nothing to reach.
    reachable.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_with_a_website_reads_the_website(client) -> None:
    response, create, reachable = await _create(
        client,
        {"name": "Crumb and Crust", "url": "https://example.com", "description": DESCRIPTION},
    )

    assert response.status_code == 201
    sent = create.await_args.kwargs
    assert sent["url"].rstrip("/") == "https://example.com"
    # The site says what the business is; a description sent with it is not drafted from.
    assert sent["description"] is None
    reachable.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("description", [None, "   "])
async def test_create_from_a_name_alone_is_passed_on_with_nothing_to_read(
    client, description
) -> None:
    # Nobody is stopped at the form (revnix/rext-control#905): the workspace is set up later.
    body = {"name": "Crumb and Crust"} | ({"description": description} if description else {})
    response, create, reachable = await _create(client, body)

    assert response.status_code == 201
    sent = create.await_args.kwargs
    assert (sent["url"], sent["description"]) == (None, None)
    reachable.assert_not_awaited()


# One request a test: the shared session's transaction ends with the request that commits it.


@pytest.mark.asyncio
async def test_create_judges_the_description_once_trimmed(client) -> None:
    full = "x" * 1000
    response, create, _ = await _create(
        client, {"name": "Crumb and Crust", "description": f"   {full}\n\n"}
    )

    assert response.status_code == 201
    assert create.await_args.kwargs["description"] == full


@pytest.mark.asyncio
async def test_create_is_not_refused_for_a_description_it_does_not_use(client) -> None:
    # Sent with a website it is not used, so its length refuses nothing.
    response, create, _ = await _create(
        client,
        {"name": "Crumb and Crust", "url": "https://example.com", "description": "x" * 5000},
    )

    assert response.status_code == 201
    assert create.await_args.kwargs["description"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": "Crumb and Crust", "description": "We bake bread."}, "description"),
        ({"name": "Crumb and Crust", "description": "x" * 1001}, "description"),
    ],
)
async def test_create_says_which_field_is_missing_or_too_short(client, body, field) -> None:
    response, create, _ = await _create(client, body)

    assert response.status_code == 422
    create.assert_not_awaited()
    # The refusal names the field, so the form can say it beside it.
    assert f"'field': '{field}'" in str(response.json())
