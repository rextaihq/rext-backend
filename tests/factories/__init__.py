"""
Test data factories for creating model instances.

Uses async-factory-boy for async SQLAlchemy support.
"""

import factory
from factory import Faker, LazyFunction, LazyAttribute, SubFactory
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

# Import models
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.content_models.content import Content
from src.api.models.topic_models.topic_models import TopicsModel
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.roles import Role


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
    username = Faker("user_name")
    display_name = Faker("name")
    password_hash = "$2b$12$KIXqXqz5Y5rZK5Y5rZK5YO"  # bcrypt hash of "password123"
    status = "active"
    email_verified = True
    created_at = LazyFunction(lambda: datetime.utcnow())
    updated_at = LazyFunction(lambda: datetime.utcnow())
    login_count = 0
    failed_login_attempts = 0
    last_login_at = None
    password_changed_at = None
    deactivated_at = None


class WorkspaceFactory(AsyncFactory):
    """Factory for WorkspaceModel"""

    class Meta:
        model = WorkspaceModel

    id = LazyFunction(uuid4)
    user_id = LazyFunction(uuid4)  # Override this in tests with actual user.id
    name = Faker("company")
    slug = LazyAttribute(lambda o: o.name.lower().replace(" ", "-").replace(",", "").replace(".", ""))
    description = Faker("catch_phrase")
    url = Faker("url")
    created_at = LazyFunction(lambda: datetime.utcnow())
    updated_at = LazyFunction(lambda: datetime.utcnow())

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
    invitation_id = None
    status = "active"
    is_default = False
    joined_at = LazyFunction(lambda: datetime.utcnow())
    last_activity_at = LazyFunction(lambda: datetime.utcnow())


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
    created_at = LazyFunction(lambda: datetime.utcnow())
    updated_at = LazyFunction(lambda: datetime.utcnow())

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


class TopicFactory(AsyncFactory):
    """Factory for TopicsModel"""

    class Meta:
        model = TopicsModel

    id = LazyFunction(uuid4)
    workspace_id = LazyFunction(uuid4)  # Override this in tests with actual workspace.id
    title = Faker("sentence", nb_words=5)
    angle = Faker("sentence", nb_words=8)
    description = Faker("text", max_nb_chars=200)
    channel_fit = ["Website", "Social Media"]
    audience_fit = ["Professionals", "Businesses"]
    why_it_works = Faker("text", max_nb_chars=150)
    scores = {
        "relevance": 0.8,
        "seo_potential": 0.85,
        "trend_level": 0.75,
        "uniqueness": 0.9,
        "reader_interest": 0.8,
        "actionable_potential": 0.85,
        "brand_alignment": 0.9,
        "controversy": 0.2
    }
    tags = ["business", "strategy", "growth"]
    approved = False
    approved_at = None
    suggested_defaults = {}
    goal_alignment = {}
    content_guidance = {}
    audience_insights = {}
    internal_research_config = {}
    user_settings = {}
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    async def create(cls, **kwargs):
        """Create topic, automatically creating workspace if workspace_id not provided"""
        if 'workspace_id' not in kwargs:
            # Create a workspace first to satisfy foreign key
            workspace = await WorkspaceFactory.create()
            kwargs['workspace_id'] = workspace.id
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
    created_at = LazyFunction(lambda: datetime.utcnow())
    updated_at = LazyFunction(lambda: datetime.utcnow())


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
    created_at = LazyFunction(lambda: datetime.utcnow())
    expires_at = LazyFunction(lambda: datetime.utcnow() + __import__("datetime").timedelta(days=7))

    @classmethod
    async def create(cls, **kwargs):
        """Create invitation with auto-dependencies"""
        session: AsyncSession = cls._session
        
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
