"""Workspace personas management routes."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.content_models.content import Content
from src.api.models.knowledge_models.persona_model import Persona
from src.api.schema.persona_schema import PersonaCreate, PersonaUpdate
from src.api.schema.response.persona_responses import PersonaListResponse, PersonaResponse
from src.api.schema.response_schemas import GenericResponse, SuccessResponse
from src.api.security.dependencies import get_current_user
from src.utils.logger import logger
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.storage import resolve_avatar_url
from src.utils.workspace_utils import resolve_workspace_for_route

router = APIRouter(tags=["workspace-personas"])


@router.get("/{workspace_id}/personas", response_model=SuccessResponse[PersonaListResponse])
@require_permissions("persona.read", workspace_scoped=True)
@db_transaction_handler("get all workspace personas", auto_commit=False)
async def list_workspace_personas(
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Get all personas for a workspace.

    Personas are extracted from website content during workspace creation
    or can be created manually.
    """
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user
    )

    # Fetch personas
    result = await db.execute(
        select(Persona)
        .where(Persona.workspace_id == workspace.id)
        .order_by(Persona.created_at.desc())
    )
    personas = result.scalars().all()

    # How many of the workspace's articles each persona wrote (the trash left out, as
    # the library leaves it out): the dashboard's persona table shows it.
    counts = await db.execute(
        select(Content.persona_id, func.count(Content.id))
        .where(
            Content.workspace_id == workspace.id,
            Content.persona_id.is_not(None),
            Content.deleted_at.is_(None),
        )
        .group_by(Content.persona_id)
    )
    article_counts = dict(counts.all())

    payloads = []
    for persona in personas:
        payload = _persona_payload(persona)
        payload["article_count"] = article_counts.get(persona.id, 0)
        payloads.append(payload)

    return success(
        data={"personas": payloads, "total_count": len(personas)},
        request=request,
        message="Workspace personas retrieved successfully",
    )


@router.get(
    "/{workspace_id}/personas/{persona_id}", response_model=SuccessResponse[PersonaResponse]
)
@require_permissions("persona.read", workspace_scoped=True)
@db_transaction_handler("get single persona", auto_commit=False)
async def get_persona(
    workspace_id: str,
    persona_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Get a single persona by ID."""
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user
    )

    # Fetch persona
    result = await db.execute(
        select(Persona).where(Persona.id == UUID(persona_id), Persona.workspace_id == workspace.id)
    )
    persona = result.scalar_one_or_none()

    if not persona:
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )

    return success(
        data=_persona_payload(persona), request=request, message="Persona retrieved successfully"
    )


# Five megabytes, matching the ceiling user avatars are held to.
_MAX_AVATAR_BYTES = 5 * 1024 * 1024


@router.post("/{workspace_id}/personas/{persona_id}/avatar")
@require_permissions("persona.update", workspace_scoped=True)
@db_transaction_handler("upload persona avatar", auto_commit=True)
async def upload_persona_avatar(
    workspace_id: str,
    persona_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Upload a picture for a persona from the user's machine.

    Validated the same way user avatars are, and stored in the same bucket by
    the same service: the checks that matter here - that the bytes really are an
    image, that an SVG cannot smuggle a script in, that a decoder can open it -
    are not persona-specific, and a second implementation of them would be a
    second place for one of them to be forgotten.

    The object key is stored rather than a URL, because MinIO links are
    presigned and expire; the key is what survives.
    """
    import io

    import filetype
    from PIL import Image

    from src.config.storage_config import get_allowed_types_by_category
    from src.utils.storage import storage_service

    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user
    )
    result = await db.execute(
        select(Persona).where(Persona.id == UUID(persona_id), Persona.workspace_id == workspace.id)
    )
    persona = result.scalar_one_or_none()
    if not persona:
        raise ResourceNotFoundException(resource_type="persona", resource_id=persona_id)

    content = await file.read()
    kind = filetype.guess(content)
    if kind is None or kind.mime not in set(get_allowed_types_by_category("image")):
        raise RextValidationException(
            message="Invalid image file. Allowed formats: JPEG, PNG, GIF, WebP."
        )
    # An SVG is a document that can carry script, not merely a picture.
    if file.filename and file.filename.lower().endswith(".svg"):
        raise RextValidationException(message="SVG files are not supported for security reasons.")
    if len(content) > _MAX_AVATAR_BYTES:
        raise RextValidationException(
            message=(f"File too large. Max: 5MB, Yours: {len(content) / (1024 * 1024):.2f}MB")
        )
    try:
        Image.open(io.BytesIO(content)).verify()
    except Exception:  # noqa: BLE001 - a decoder refusing it is the answer
        raise RextValidationException(message="Image file appears to be corrupted or malformed.")

    stamp = int(datetime.now(timezone.utc).timestamp())
    object_name = f"avatars/personas/{persona_id}/avatar_{stamp}.{kind.extension}"
    if not storage_service.upload_file(
        file_data=content, object_name=object_name, content_type=kind.mime
    ):
        raise RextValidationException(message="Failed to upload image to storage.")

    previous = persona.avatar_url or ""
    persona.avatar_url = object_name
    # Uploaded by a person, so it outranks anything found or derived - the same
    # rule a pasted URL follows, for the same reason.
    persona.avatar_source = "custom"
    try:
        await db.flush()
        await db.refresh(persona)
    except Exception:
        # The row did not take the new picture, so the file we just wrote
        # belongs to nobody. Removing it here rather than leaving it is the
        # difference between a bucket that reflects the database and one that
        # accumulates the debris of every failed request.
        try:
            storage_service.delete_file(object_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not remove orphaned upload %s: %s", object_name, exc)
        raise

    # The old file goes only after the row is committed. Deleting it here would
    # mean a rollback anywhere later in the request leaves the database naming
    # a file that no longer exists - a persona whose picture is gone and cannot
    # be recovered, which is worse than a file nobody references.
    if previous.startswith("avatars/personas/"):
        _delete_after_commit(db, previous)

    logger.info(
        "persona avatar uploaded",
        extra={
            "workspace_id": str(workspace_id),
            "persona_id": str(persona_id),
            "object": object_name,
        },
    )
    return success(
        data=_persona_payload(persona),
        request=request,
        message="Avatar uploaded successfully",
    )


def _delete_after_commit(db, object_name: str) -> None:
    """Remove a stored file once the transaction that replaced it has committed.

    Ordering matters in one direction only. A file deleted before the commit is
    unrecoverable if the transaction rolls back, and the row then names a
    picture that no longer exists. A file deleted after is at worst a moment of
    duplication, and if the commit never happens it simply stays - which is why
    a rollback disarms the listener.
    """
    from sqlalchemy import event

    from src.utils.storage import storage_service

    session = db.sync_session if hasattr(db, "sync_session") else db
    # The listeners disarm themselves instead of being removed: removing a listener while
    # SQLAlchemy dispatches its event mutates the list being iterated ("deque mutated during
    # iteration"), which failed the commit with a 500 after the change had already been
    # committed (G64). They live as long as the request's session.
    armed = {"on": True}

    def _on_commit(_session) -> None:
        if not armed["on"]:
            return
        armed["on"] = False
        try:
            storage_service.delete_file(object_name)
        except Exception as exc:  # noqa: BLE001 - an orphan is not a failure
            logger.warning("could not delete previous persona avatar %s: %s", object_name, exc)

    def _on_rollback(_session) -> None:
        armed["on"] = False

    event.listen(session, "after_commit", _on_commit)
    event.listen(session, "after_rollback", _on_rollback)


async def _gravatar_or_none(email: str) -> str:
    """That address's Gravatar, or "" when it has none registered.

    Asked rather than assumed, as everywhere else: building the URL says
    nothing about whether a picture is behind it, and recording one that is not
    leaves the persona claiming a photograph the browser cannot load.
    """
    import httpx

    from src.utils.fast_scraper import USER_AGENT, gravatar_if_exists

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            return await gravatar_if_exists(client, email)
    except Exception as exc:  # noqa: BLE001 - a picture never fails a save
        logger.warning("gravatar lookup failed for a persona update: %s", exc)
        return ""


def _is_echoed_avatar(incoming: str, stored: str) -> bool:
    """Whether an avatar_url sent on update is the stored picture coming back.

    Gravatars and inline initials are derived by us, never a person's choice.
    An uploaded photo is stored as an object key and served as a presigned or
    public URL whose path ends with that key.
    """
    from urllib.parse import unquote, urlparse

    if incoming == stored or incoming.startswith(("data:", "https://www.gravatar.com/")):
        return True
    if stored and not stored.startswith(("http://", "https://", "data:")):
        return unquote(urlparse(incoming).path).endswith("/" + stored.lstrip("/"))
    return False


def _persona_payload(persona) -> dict:
    """A persona as the client should see it.

    Avatars are stored as bare object keys because the URLs this storage issues
    are presigned and expire, so every endpoint that hands one out has to turn
    it back into something a browser can fetch. Skipping that returned
    "avatars/personas/<id>/avatar_123.png" as the image source: the upload
    reported success, the record was correct, and the picture never appeared.
    """
    data = persona.to_dict()
    data["avatar_url"] = resolve_avatar_url(data.get("avatar_url"))
    return data


async def _resolve_avatar(persona_data) -> dict:
    """Decide a manually created persona's picture and record where it came from.

    The same precedence the extraction pipeline applies, so a persona a person
    types in and one the crawler found describe their picture in the same terms:
    an image the person supplied wins, a Gravatar is derived only when they gave
    an address and chose no image, and initials are drawn when they gave
    neither. Recorded rather than merely applied - a photograph and a coloured
    circle bearing someone's letters are not the same claim, and the URL alone
    does not say which it is.
    """
    from src.utils.fast_scraper import initials_avatar

    supplied = (getattr(persona_data, "avatar_url", None) or "").strip()
    email = (getattr(persona_data, "email", None) or "").strip()
    if supplied:
        return {"avatar_url": supplied, "avatar_source": "custom", "email": email or None}
    # Checked, not assumed: the URL alone ends in d=404 and shows a broken
    # image for an address with no Gravatar registered.
    if email and (derived := await _gravatar_or_none(email)):
        return {"avatar_url": derived, "avatar_source": "gravatar", "email": email}
    return {
        "avatar_url": initials_avatar(persona_data.name or ""),
        "avatar_source": "generated",
        "email": email or None,
    }


def _normalized_name(name: str):
    """A persona name as it is compared for duplicates.

    Case and repeated or surrounding whitespace are not distinctions anyone
    means to make: "Mary Jane", "mary  jane" and " Mary Jane " are one name.
    Expressed in SQL so the comparison happens in the database and two
    concurrent requests see the same answer.
    """
    return func.lower(func.regexp_replace(func.trim(name), r"\s+", " ", "g"))


async def _reject_duplicate_name(db, workspace_id, name: str, exclude_id=None) -> None:
    """Refuse a name another persona in this workspace already holds.

    This is what makes a rapid double-click on Create produce one persona
    rather than several: the second request finds the first one's row and is
    turned away. The frontend blocks the second click too, but a dropped
    connection, a retry or anything that is not the form would otherwise get
    through, and the check has to live where the row is written.
    """
    query = select(Persona.id).where(
        Persona.workspace_id == workspace_id,
        _normalized_name(Persona.name) == _normalized_name(name),
    )
    if exclude_id is not None:
        query = query.where(Persona.id != exclude_id)
    if (await db.execute(query.limit(1))).scalar_one_or_none():
        raise DuplicateResourceException(
            message=f"A persona named '{name.strip()}' already exists in this workspace",
            resource_type="persona",
            conflicting_field="name",
            conflicting_value=name.strip(),
        )


@router.post(
    "/{workspace_id}/personas",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[PersonaResponse],
)
@require_permissions("persona.create", workspace_scoped=True)
@db_transaction_handler("create persona", auto_commit=True)
async def create_persona(
    workspace_id: str,
    persona_data: PersonaCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Create a new persona manually."""
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user
    )

    await _reject_duplicate_name(db, workspace.id, persona_data.name)

    def _to_csv(v: list | None) -> str | None:
        return ", ".join(v) if v else None

    # Create persona
    persona = Persona(
        workspace_id=workspace.id,
        name=persona_data.name,
        description=persona_data.description,
        full_name=persona_data.full_name,
        professional_title=persona_data.professional_title,
        areas_of_expertise=persona_data.areas_of_expertise,
        tone_of_voice=persona_data.tone_of_voice,
        bio=persona_data.bio,
        linkedin_url=persona_data.linkedin_url,
        demographics=persona_data.demographics,
        pain_points=_to_csv(persona_data.pain_points),
        goals=_to_csv(persona_data.goals),
        behaviors=_to_csv(persona_data.behaviors),
        **(await _resolve_avatar(persona_data)),
    )

    db.add(persona)
    await db.flush()
    await db.refresh(persona)

    logger.info(
        "Created persona",
        extra={
            "workspace_id": str(workspace.id),
            "persona_id": str(persona.id),
        },
    )

    return created(
        data=_persona_payload(persona), request=request, message="Persona created successfully"
    )


@router.put(
    "/{workspace_id}/personas/{persona_id}", response_model=SuccessResponse[PersonaResponse]
)
@require_permissions("persona.update", workspace_scoped=True)
@db_transaction_handler("update persona", auto_commit=True)
async def update_persona(
    workspace_id: str,
    persona_id: str,
    persona_data: PersonaUpdate,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Update an existing persona."""
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user
    )

    # Fetch persona
    result = await db.execute(
        select(Persona).where(Persona.id == UUID(persona_id), Persona.workspace_id == workspace.id)
    )
    persona = result.scalar_one_or_none()

    if not persona:
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )

    stored_avatar = persona.avatar_url or ""
    stored_source = persona.avatar_source
    stored_email = (persona.email or "").strip().lower()

    # A rename onto another persona's name is the same collision as creating
    # one; the persona being edited is excluded so re-saving it is not a clash
    # with itself.
    if persona_data.name is not None:
        await _reject_duplicate_name(db, workspace.id, persona_data.name, exclude_id=persona.id)

    # Update fields — coerce list fields to match DB column types
    _TEXT_LIST_FIELDS = {"pain_points", "goals", "behaviors"}
    update_data = persona_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in _TEXT_LIST_FIELDS and isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        elif field == "areas_of_expertise" and isinstance(value, list):
            # Normalize: unwrap any stringified JSON items (e.g. '["foo"]' → 'foo')
            import json

            normalized = []
            for item in value:
                if isinstance(item, str):
                    try:
                        parsed = json.loads(item)
                        if isinstance(parsed, list):
                            normalized.extend(str(i).strip('"') for i in parsed)
                        else:
                            normalized.append(str(parsed).strip('"'))
                    except (json.JSONDecodeError, ValueError):
                        normalized.append(item.strip('"'))
                else:
                    normalized.append(item)
            value = normalized
        setattr(persona, field, value)

    # The picture follows from what the person just changed. The edit form
    # sends every field back, avatar_url and email included, so their presence
    # says nothing; only a value that differs from the stored one is a choice.
    #   - a new image URL wins;
    #   - a new email fetches its Gravatar, which replaces any picture,
    #     an uploaded one included - asking for it is the person's choice;
    #   - otherwise the stored picture stays, and only a derived one (Gravatar,
    #     initials) follows the current email and name.
    # An upload (POST .../avatar) always replaces whatever is there.
    message = "Persona updated successfully"
    if update_data.keys() & {"avatar_url", "email", "name"}:
        from src.utils.fast_scraper import initials_avatar

        incoming = (update_data.get("avatar_url") or "").strip()
        email = (persona.email or "").strip()
        email_changed = "email" in update_data and email.lower() != stored_email
        if (
            "avatar_url" in update_data
            and incoming
            and not _is_echoed_avatar(incoming, stored_avatar)
        ):
            persona.avatar_url, persona.avatar_source = incoming, "custom"
        else:
            # Keep the stored value: for an upload that is the object key, and
            # writing back the presigned URL the form echoed stores a link that
            # expires within the hour.
            cleared = "avatar_url" in update_data and not incoming
            persona.avatar_url = None if cleared else (stored_avatar or None)
            persona.avatar_source = None if cleared else stored_source
            current = persona.avatar_url or ""
            derived_picture = (
                not current
                or current.startswith("data:")
                or persona.avatar_source in ("gravatar", "generated")
            )
            gravatar = (
                await _gravatar_or_none(email)
                if email and (email_changed or derived_picture)
                else ""
            )
            if gravatar:
                persona.avatar_url, persona.avatar_source = gravatar, "gravatar"
            elif derived_picture:
                persona.avatar_url = initials_avatar(persona.name or "")
                persona.avatar_source = "generated"
            if email and email_changed and not gravatar:
                message = (
                    "Persona updated. No Gravatar is registered for this email, "
                    "so the picture was not changed."
                )
        # The uploaded file the persona no longer shows goes once this commits.
        if stored_avatar.startswith("avatars/personas/") and persona.avatar_url != stored_avatar:
            _delete_after_commit(db, stored_avatar)

    persona.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(persona)

    logger.info(
        "Updated persona",
        extra={
            "workspace_id": str(workspace.id),
            "persona_id": str(persona.id),
        },
    )

    return success(data=_persona_payload(persona), request=request, message=message)


@router.delete(
    "/{workspace_id}/personas/{persona_id}",
    status_code=status.HTTP_200_OK,
    response_model=SuccessResponse[GenericResponse],
)
@require_permissions("persona.delete", workspace_scoped=True)
@db_transaction_handler("delete persona", auto_commit=True)
async def delete_persona(
    workspace_id: str,
    persona_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete a persona."""
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user
    )

    # Fetch persona
    result = await db.execute(
        select(Persona).where(Persona.id == UUID(persona_id), Persona.workspace_id == workspace.id)
    )
    persona = result.scalar_one_or_none()

    if not persona:
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )

    await db.delete(persona)
    logger.info(
        "Deleted persona",
        extra={
            "workspace_id": str(workspace.id),
            "persona_id": str(persona.id),
        },
    )

    return success(data={}, request=request, message="Persona deleted successfully")


__all__ = ["router"]
