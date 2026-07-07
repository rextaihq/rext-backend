"""
Unit tests for WorkspaceGoogleConnection model.

Tests the WorkspaceGoogleConnection model structure, relationships, and constraints.
"""

import uuid
from datetime import datetime, timezone
import pytest


def test_workspace_google_connection_model_structure():
    """Test that WorkspaceGoogleConnection model has all required attributes."""
    from src.api.models.integrations import WorkspaceGoogleConnection
    
    # Check table name
    assert WorkspaceGoogleConnection.__tablename__ == "workspace_google_connections"
    
    # Check all required columns exist
    columns = {c.name for c in WorkspaceGoogleConnection.__table__.columns}
    required_columns = {
        'id', 'workspace_id', 'oauth_account_id', 'gsc_site_url', 
        'ga4_property_id', 'last_synced_at', 'last_backfill_completed_at',
        'created_at', 'updated_at'
    }
    assert required_columns.issubset(columns), f"Missing columns: {required_columns - columns}"


def test_workspace_google_connection_unique_constraint():
    """Test that workspace_id has a unique constraint."""
    from src.api.models.integrations import WorkspaceGoogleConnection
    
    # Check unique constraint exists
    constraints = WorkspaceGoogleConnection.__table__.constraints
    unique_constraints = [c for c in constraints if hasattr(c, 'columns') and 'workspace_id' in [col.name for col in c.columns]]
    
    assert len(unique_constraints) > 0, "workspace_id should have a unique constraint"


def test_workspace_google_connection_foreign_keys():
    """Test that foreign key constraints are properly defined."""
    from src.api.models.integrations import WorkspaceGoogleConnection
    
    foreign_keys = list(WorkspaceGoogleConnection.__table__.foreign_keys)
    
    # Check workspace_id foreign key with CASCADE
    workspace_fk = [fk for fk in foreign_keys if 'workspace_id' in str(fk.parent)]
    assert len(workspace_fk) == 1, "workspace_id should have a foreign key"
    assert workspace_fk[0].ondelete == "CASCADE", "workspace_id should have CASCADE on delete"
    
    # Check oauth_account_id foreign key with SET NULL
    oauth_fk = [fk for fk in foreign_keys if 'oauth_account_id' in str(fk.parent)]
    assert len(oauth_fk) == 1, "oauth_account_id should have a foreign key"
    assert oauth_fk[0].ondelete == "SET NULL", "oauth_account_id should have SET NULL on delete"


def test_workspace_google_connection_indexes():
    """Test that indexes are properly defined."""
    from src.api.models.integrations import WorkspaceGoogleConnection
    
    # Get all indexed columns
    indexed_columns = set()
    for col in WorkspaceGoogleConnection.__table__.columns:
        if col.index or col.unique:
            indexed_columns.add(col.name)
    
    # Check required indexes
    assert 'workspace_id' in indexed_columns, "workspace_id should be indexed"
    assert 'oauth_account_id' in indexed_columns, "oauth_account_id should be indexed"


def test_workspace_google_connection_relationships():
    """Test that relationships are properly defined."""
    from src.api.models.integrations import WorkspaceGoogleConnection
    import inspect
    
    # Get all relationship attributes
    relationships = [
        name for name, obj in inspect.getmembers(WorkspaceGoogleConnection)
        if hasattr(obj, 'property') and hasattr(obj.property, 'direction')
    ]
    
    assert 'workspace' in relationships, "Should have workspace relationship"
    assert 'oauth_account' in relationships, "Should have oauth_account relationship"


def test_workspace_google_connection_mixins():
    """Test that model inherits from required mixins."""
    from src.api.models.integrations import WorkspaceGoogleConnection
    from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin
    from src.api.models.base import SerializableMixin
    
    # Check mixin inheritance
    assert issubclass(WorkspaceGoogleConnection, UUIDPrimaryKeyMixin), "Should inherit from UUIDPrimaryKeyMixin"
    assert issubclass(WorkspaceGoogleConnection, TimestampMixin), "Should inherit from TimestampMixin"
    assert issubclass(WorkspaceGoogleConnection, SerializableMixin), "Should inherit from SerializableMixin"


def test_workspace_google_connection_column_types():
    """Test that columns have correct types and constraints."""
    from src.api.models.integrations import WorkspaceGoogleConnection
    from sqlalchemy import String, DateTime
    from sqlalchemy.dialects.postgresql import UUID
    
    columns = {c.name: c for c in WorkspaceGoogleConnection.__table__.columns}
    
    # Check UUID columns
    assert isinstance(columns['id'].type, UUID), "id should be UUID type"
    assert isinstance(columns['workspace_id'].type, UUID), "workspace_id should be UUID type"
    assert isinstance(columns['oauth_account_id'].type, UUID), "oauth_account_id should be UUID type"
    
    # Check String columns
    assert isinstance(columns['gsc_site_url'].type, String), "gsc_site_url should be String type"
    assert isinstance(columns['ga4_property_id'].type, String), "ga4_property_id should be String type"
    
    # Check DateTime columns
    assert isinstance(columns['last_synced_at'].type, DateTime), "last_synced_at should be DateTime type"
    assert isinstance(columns['last_backfill_completed_at'].type, DateTime), "last_backfill_completed_at should be DateTime type"
    assert isinstance(columns['created_at'].type, DateTime), "created_at should be DateTime type"
    assert isinstance(columns['updated_at'].type, DateTime), "updated_at should be DateTime type"
    
    # Check nullable constraints
    assert columns['workspace_id'].nullable is False, "workspace_id should be NOT NULL"
    assert columns['oauth_account_id'].nullable is True, "oauth_account_id should be nullable"
    assert columns['gsc_site_url'].nullable is True, "gsc_site_url should be nullable"
    assert columns['ga4_property_id'].nullable is True, "ga4_property_id should be nullable"
