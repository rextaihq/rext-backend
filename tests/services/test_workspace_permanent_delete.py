"""
Guard for WorkspaceService.permanently_delete_workspace().

Permanent deletion is the only hard delete of a workspace row, so every table
pointing at workspace.id has to survive it deliberately: either the FK carries
an ondelete rule, or the service deletes the rows itself.

user_roles is the one exception — its workspace_id is a plain nullable FK with
no ondelete rule. Left to SQLAlchemy's default, deleting the parent would UPDATE
those rows to workspace_id = NULL, and a UserRole with a NULL workspace is an
unscoped, platform-wide grant. So the service deletes them explicitly.

This test fails when a new child table appears without an ondelete rule (that
table would silently orphan or block the delete), and when user_roles gains one
(at which point the explicit delete is dead code and can go).
"""

import importlib
import inspect
import pkgutil

import src.api.models
from src.api.database.base import Base
from src.services.workspace_service import WorkspaceService


def _register_every_model():
    """
    Import every module under src.api.models so the metadata is complete.

    src.api.models.__init__ deliberately imports only some models to dodge
    circular imports, and scanning a partial registry would miss exactly the new
    table this test exists to catch.
    """
    for module in pkgutil.walk_packages(
        src.api.models.__path__, prefix="src.api.models."
    ):
        importlib.import_module(module.name)


_register_every_model()

# Tables the service cleans up by hand instead of relying on the FK.
EXPLICITLY_CLEANED = {"user_roles"}


def _workspace_foreign_keys():
    """Every FK across the model metadata that points at workspace.id."""
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.column.table.name == "workspace" and fk.column.name == "id":
                yield table.name, fk


def test_every_workspace_child_fk_is_handled():
    unhandled = {
        table_name
        for table_name, fk in _workspace_foreign_keys()
        if fk.ondelete is None and table_name not in EXPLICITLY_CLEANED
    }

    assert not unhandled, (
        f"Tables {sorted(unhandled)} reference workspace.id with no ondelete rule. "
        "Permanently deleting a workspace will orphan or NULL their rows. Either add "
        "ondelete='CASCADE'/'SET NULL' to the FK, or delete them explicitly in "
        "WorkspaceService.permanently_delete_workspace() and list them here."
    )


def test_user_roles_still_needs_the_explicit_cleanup():
    ondelete_rules = {
        fk.ondelete for name, fk in _workspace_foreign_keys() if name == "user_roles"
    }

    assert ondelete_rules == {None}, (
        "user_roles.workspace_id now has an ondelete rule. The explicit "
        "delete(UserRole) in WorkspaceService.permanently_delete_workspace() is "
        "redundant — drop it and remove user_roles from EXPLICITLY_CLEANED."
    )

    source = inspect.getsource(WorkspaceService.permanently_delete_workspace)
    assert "delete(UserRole)" in source, (
        "permanently_delete_workspace() no longer deletes UserRole rows. Without it, "
        "members holding workspace_owner on the deleted workspace keep the role as an "
        "unscoped, platform-wide grant."
    )


def test_permanent_delete_requires_an_already_deleted_workspace():
    """
    The route must never be able to destroy a live workspace. That gate is
    get_deleted_workspace(), which filters on deleted_at IS NOT NULL and raises
    ResourceNotFoundException otherwise.
    """
    source = inspect.getsource(WorkspaceService.permanently_delete_workspace)

    assert "get_deleted_workspace(" in source, (
        "permanently_delete_workspace() must load the workspace via "
        "get_deleted_workspace(), which is what restricts it to soft-deleted rows."
    )
    assert "verify_user_is_workspace_owner(" in source, (
        "permanently_delete_workspace() must verify workspace ownership first."
    )


def test_purge_storage_routes_by_backend_and_never_raises(monkeypatch):
    """
    The cascade only removes rows, so the objects and vectors are cleaned by
    _purge_workspace_storage(). It deletes knowledge files from MinIO and vectors,
    and must swallow failures: raising here would roll back a delete the user
    already asked for and leave an unremovable workspace.
    """
    import asyncio
    from uuid import uuid4

    import src.utils.file_upload_utils as file_upload_utils
    import src.utils.vector_store as vector_store

    minio_deleted, vectors_deleted = [], []

    async def fake_minio_delete(path):
        minio_deleted.append(path)
        if path == "workspaces/kb/boom.pdf":
            raise RuntimeError("MinIO down")
        return True

    monkeypatch.setattr(file_upload_utils, "delete_file", fake_minio_delete)
    monkeypatch.setattr(
        vector_store, "delete_vectors", lambda **kwargs: vectors_deleted.append(kwargs)
    )

    workspace_id = uuid4()
    service = WorkspaceService(db=None)

    asyncio.run(
        service._purge_workspace_storage(
            workspace_id,
            knowledge_paths=["workspaces/kb/doc.pdf", "workspaces/kb/boom.pdf", None],
        )
    )

    assert minio_deleted == [
        "workspaces/kb/doc.pdf",
        "workspaces/kb/boom.pdf",
    ]
    assert len(vectors_deleted) == 1
    assert vectors_deleted[0]["workspace_id"] == str(workspace_id)


def test_permanent_delete_purges_external_storage():
    source = inspect.getsource(WorkspaceService.permanently_delete_workspace)

    assert "_purge_workspace_storage(" in source, (
        "permanently_delete_workspace() no longer cleans external storage. The FK "
        "cascade only removes rows, so the uploaded objects and FAISS vectors would "
        "be orphaned."
    )
