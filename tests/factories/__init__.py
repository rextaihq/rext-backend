"""
Test data factories for creating model instances.

Uses async-factory-boy for async SQLAlchemy support.
"""

import factory
from factory import Faker, LazyFunction, LazyAttribute
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

# Import models
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.content_models.content import Content

from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.roles import Role
from src.api.models.knowledge_models.knowledge_model import KnowledgeBase, Website, KnowledgeFiles, TextKnowledge
from src.api.models.knowledge_models.persona_model import Persona


# Base async factory
class AsyncFactory(factory.Factory):
    """Base async factory for SQLAlchemy models"""

    class Meta:
        abstract = True

    _session = None  # Will be set by setup_factories fixture

    @classmethod
    async def create(cls, **kwargs):
        """Async create method"""
        obj = cls.build(**kwargs)
        session: AsyncSession = cls._session
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    @classmethod
    async def create_batch(cls, size, **kwargs):
        """Create multiple instances"""
        return [await cls.create(**kwargs) for _ in range(size)]


class UserFactory(AsyncFactory):
    """Factory for Users model"""

    class Meta:
        model = Users

    id = LazyFunction(uuid4)
    email = Faker("email")
    display_name = Faker("name")
    password_hash = "$2b$12$KIXqXqz5Y5rZK5Y5rZK5YO"  # bcrypt hash of "password123"
    status = "active"
    email_verified = True
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = LazyFunction(lambda: datetime.now(timezone.utc))
    login_count = 0
    failed_login_attempts = 0


class WorkspaceFactory(AsyncFactory):
    """Factory for WorkspaceModel"""

    class Meta:
        model = WorkspaceModel

    id = LazyFunction(uuid4)
    user_id = LazyFunction(uuid4)  # Override this in tests with actual user.id
    name = Faker("company")
    slug = LazyAttribute(lambda o: o.name.lower().replace(" ", "-").replace(",", "").replace(".", ""))
    url = Faker("url")
    timezone = "UTC"
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    async def create(cls, **kwargs):
        """Create workspace, automatically creating user if user_id not provided"""
        if 'user_id' not in kwargs:
            # Create a user first to satisfy foreign key
            user = await UserFactory.create()
            kwargs['user_id'] = user.id
        return await super().create(**kwargs)


class WorkspaceMemberFactory(AsyncFactory):
    """Factory for WorkspaceMembers"""

    class Meta:
        model = WorkspaceMembers

    id = LazyFunction(uuid4)
    workspace_id = LazyFunction(uuid4)
    user_id = LazyFunction(uuid4)
    status = "active"
    is_default = False
    joined_at = LazyFunction(lambda: datetime.now(timezone.utc))


class ContentFactory(AsyncFactory):
    """Factory for Content model"""

    class Meta:
        model = Content

    id = LazyFunction(uuid4)
    workspace_id = LazyFunction(uuid4)
    created_by_user_id = LazyFunction(uuid4)
    author_id = LazyAttribute(lambda o: o.created_by_user_id)
    title = Faker("sentence", nb_words=6)
    slug = LazyAttribute(lambda o: o.title.lower().replace(" ", "-").replace(".", ""))
    body_markdown = Faker("text", max_nb_chars=500)
    content_format = "Markdown"
    status = "draft"
    content_language = "English"
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    async def create(cls, **kwargs):
        """Create content with valid workspace and user foreign keys."""
        if 'workspace_id' not in kwargs:
            workspace = await WorkspaceFactory.create()
            kwargs['workspace_id'] = workspace.id

        if 'created_by_user_id' not in kwargs:
            user = await UserFactory.create()
            kwargs['created_by_user_id'] = user.id

        # Default author to creator if not provided
        kwargs.setdefault('author_id', kwargs['created_by_user_id'])

        return await super().create(**kwargs)


class RoleFactory(AsyncFactory):
    """Factory for Role model"""

    class Meta:
        model = Role

    id = LazyFunction(uuid4)
    name = Faker("job")
    display_name = LazyAttribute(lambda o: o.name.title())
    description = Faker("sentence")
    hierarchy_level = 0
    is_system_role = False
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = LazyFunction(lambda: datetime.now(timezone.utc))


class InvitationFactory(AsyncFactory):
    """Factory for UserInvitations model"""

    class Meta:
        model = UserInvitations

    id = LazyFunction(uuid4)
    email = Faker("email")
    workspace_id = LazyFunction(uuid4)
    role_id = LazyFunction(uuid4)
    invited_by_user_id = LazyFunction(uuid4)
    invitation_token = LazyFunction(lambda: f"token_{uuid4().hex[:16]}")
    status = "pending"
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))
    expires_at = LazyAttribute(lambda o: datetime.now(timezone.utc) + __import__("datetime").timedelta(days=7))

    @classmethod
    async def create(cls, **kwargs):
        """Create invitation with auto-dependencies"""
        if "workspace_id" not in kwargs:
            workspace = await WorkspaceFactory.create()
            kwargs["workspace_id"] = workspace.id
        
        if "role_id" not in kwargs:
            role = await RoleFactory.create()
            kwargs["role_id"] = role.id
        
        if "invited_by_user_id" not in kwargs:
            user = await UserFactory.create()
            kwargs["invited_by_user_id"] = user.id

        return await super().create(**kwargs)


class KnowledgeBaseFactory(AsyncFactory):
    """Factory for KnowledgeBase model"""

    class Meta:
        model = KnowledgeBase

    id = LazyFunction(uuid4)
    workspace_id = LazyFunction(uuid4)
    name = Faker("catch_phrase")
    description = Faker("text", max_nb_chars=200)
    type = "custom"
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    async def create(cls, **kwargs):
        """Create knowledge base, automatically creating workspace if workspace_id not provided"""
        if 'workspace_id' not in kwargs:
            workspace = await WorkspaceFactory.create()
            kwargs['workspace_id'] = workspace.id
        return await super().create(**kwargs)


class WebsiteFactory(AsyncFactory):
    """Factory for Website model"""

    class Meta:
        model = Website

    id = LazyFunction(uuid4)
    workspace_id = LazyFunction(uuid4)
    knowledge_base_id = LazyFunction(uuid4)
    url = Faker("url")
    status = "trained"
    char_count = 1000
    word_count = 200

    @classmethod
    async def create(cls, **kwargs):
        """Create website with auto-dependencies"""
        if 'workspace_id' not in kwargs:
            workspace = await WorkspaceFactory.create()
            kwargs['workspace_id'] = workspace.id

        if 'knowledge_base_id' not in kwargs:
            kb = await KnowledgeBaseFactory.create(workspace_id=kwargs['workspace_id'])
            kwargs['knowledge_base_id'] = kb.id

        return await super().create(**kwargs)


class KnowledgeFilesFactory(AsyncFactory):
    """Factory for KnowledgeFiles model"""

    class Meta:
        model = KnowledgeFiles

    id = LazyFunction(uuid4)
    workspace_id = LazyFunction(uuid4)
    knowledge_base_id = LazyFunction(uuid4)
    file_name = Faker("file_name")
    file_type = "application/pdf"
    file_size = 1024000
    file_path = LazyAttribute(lambda o: f"/uploads/{o.file_name}")
    status = "completed"
    file_hash = LazyFunction(lambda: f"hash_{uuid4().hex}")
    mime_type = "application/pdf"
    chunk_count = 10
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    async def create(cls, **kwargs):
        """Create knowledge file with auto-dependencies"""
        if 'workspace_id' not in kwargs:
            workspace = await WorkspaceFactory.create()
            kwargs['workspace_id'] = workspace.id

        if 'knowledge_base_id' not in kwargs:
            kb = await KnowledgeBaseFactory.create(workspace_id=kwargs['workspace_id'])
            kwargs['knowledge_base_id'] = kb.id

        return await super().create(**kwargs)


class TextKnowledgeFactory(AsyncFactory):
    """Factory for TextKnowledge model"""

    class Meta:
        model = TextKnowledge

    id = LazyFunction(uuid4)
    workspace_id = LazyFunction(uuid4)
    knowledge_base_id = LazyFunction(uuid4)
    title = Faker("sentence", nb_words=5)
    content = Faker("text", max_nb_chars=500)
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    async def create(cls, **kwargs):
        """Create text knowledge with auto-dependencies"""
        if 'workspace_id' not in kwargs:
            workspace = await WorkspaceFactory.create()
            kwargs['workspace_id'] = workspace.id

        if 'knowledge_base_id' not in kwargs:
            kb = await KnowledgeBaseFactory.create(workspace_id=kwargs['workspace_id'])
            kwargs['knowledge_base_id'] = kb.id

        return await super().create(**kwargs)


class PersonaFactory(AsyncFactory):
    """Factory for Persona model"""

    class Meta:
        model = Persona

    id = LazyFunction(uuid4)
    workspace_id = LazyFunction(uuid4)
    name = Faker("name")
    role = Faker("job")
    tone_of_voice = "Professional"
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    async def create(cls, **kwargs):
        """Create persona with auto-dependencies"""
        if 'workspace_id' not in kwargs:
            workspace = await WorkspaceFactory.create()
            kwargs['workspace_id'] = workspace.id
        return await super().create(**kwargs)
