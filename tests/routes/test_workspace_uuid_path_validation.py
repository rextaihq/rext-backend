"""
The workspace trash routes take a UUID, not a slug.

Both used to declare workspace_id: str and parse it with UUID(workspace_id) in
the handler body, so a malformed id raised a bare ValueError that the generic
except-Exception in db_transaction_handler turned into a 500. Typing the path
parameter lets FastAPI reject it with a 422 before the handler runs.

No fixtures: the router is mounted on a bare app so the check is about request
validation only, and needs neither a database nor a token.
"""

import inspect

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.workspaces import workspace_core


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(workspace_core.router, prefix="/workspaces")
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "method,path",
    [
        ("delete", "/workspaces/not-a-uuid/permanent"),
        ("post", "/workspaces/not-a-uuid/restore"),
    ],
)
def test_malformed_workspace_id_is_a_422_not_a_500(client, method, path):
    response = getattr(client, method)(path)

    assert response.status_code == 422, response.text
    errors = response.json()["detail"]
    assert any(
        error["loc"][-1] == "workspace_id" and "uuid" in error["type"] for error in errors
    ), errors


@pytest.mark.parametrize(
    "endpoint",
    [
        workspace_core.permanently_delete_workspace_endpoint,
        workspace_core.restore_workspace_endpoint,
    ],
)
def test_handlers_do_not_parse_the_path_parameter_themselves(endpoint):
    source = inspect.getsource(endpoint)

    assert "UUID(workspace_id)" not in source, (
        f"{endpoint.__name__} parses workspace_id by hand again. A malformed id "
        "raises ValueError inside the handler, which surfaces as a 500 instead "
        "of a validation error — declare the parameter as UUID instead."
    )
