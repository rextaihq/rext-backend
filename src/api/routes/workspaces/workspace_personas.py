"""Workspace personas management routes."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException
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
@require_permissions("workspace.read", workspace_scoped=True)
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
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)
    
    # Fetch personas
    result = await db.execute(
        select(Persona)
        .where(Persona.workspace_id == workspace.id)
        .order_by(Persona.created_at.desc())
    )
    personas = result.scalars().all()
    
    return success(
        data={
            "personas": [_persona_payload(p) for p in personas],
            "total_count": len(personas)
        },
        request=request,
        message="Workspace personas retrieved successfully"
    )


@router.get("/{workspace_id}/personas/{persona_id}", response_model=SuccessResponse[PersonaResponse])
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("get single persona", auto_commit=False)
async def get_persona(
    workspace_id: str,
    persona_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Get a single persona by ID."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)
    
    # Fetch persona
    result = await db.execute(
        select(Persona).where(
            Persona.id == UUID(persona_id),
            Persona.workspace_id == workspace.id
        )
    )
    persona = result.scalar_one_or_none()
    
    if not persona:
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )
    
    return success(
        data=_persona_payload(persona),
        request=request,
        message="Persona retrieved successfully"
    )


# Five megabytes, matching the ceiling user avatars are held to.
_MAX_AVATAR_BYTES = 5 * 1024 * 1024


@router.post("/{workspace_id}/personas/{persona_id}/avatar")
@require_permissions("workspace.update", workspace_scoped=True)
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
        db=db, workspace_identifier=workspace_id, user=user)
    result = await db.execute(
        select(Persona).where(Persona.id == UUID(persona_id),
                              Persona.workspace_id == workspace.id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise ResourceNotFoundException(resource_type="persona",
                                        resource_id=persona_id)

    content = await file.read()
    kind = filetype.guess(content)
    if kind is None or kind.mime not in set(get_allowed_types_by_category("image")):
        raise RextValidationException(
            message="Invalid image file. Allowed formats: JPEG, PNG, GIF, WebP.")
    # An SVG is a document that can carry script, not merely a picture.
    if file.filename and file.filename.lower().endswith(".svg"):
        raise RextValidationException(
            message="SVG files are not supported for security reasons.")
    if len(content) > _MAX_AVATAR_BYTES:
        raise RextValidationException(
            message=(f"File too large. Max: 5MB, Yours: "
                     f"{len(content) / (1024 * 1024):.2f}MB"))
    try:
        Image.open(io.BytesIO(content)).verify()
    except Exception:  # noqa: BLE001 - a decoder refusing it is the answer
        raise RextValidationException(
            message="Image file appears to be corrupted or malformed.")

    stamp = int(datetime.now(timezone.utc).timestamp())
    object_name = (f"avatars/personas/{persona_id}/"
                   f"avatar_{stamp}.{kind.extension}")
    if not storage_service.upload_file(file_data=content, object_name=object_name,
                                       content_type=kind.mime):
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
            logger.warning("could not remove orphaned upload %s: %s",
                           object_name, exc)
        raise

    # The old file goes only after the row is committed. Deleting it here would
    # mean a rollback anywhere later in the request leaves the database naming
    # a file that no longer exists - a persona whose picture is gone and cannot
    # be recovered, which is worse than a file nobody references.
    if previous.startswith("avatars/personas/"):
        _delete_after_commit(db, previous)

    logger.info("persona avatar uploaded",
                extra={"workspace_id": str(workspace_id),
                       "persona_id": str(persona_id), "object": object_name})
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
    the listener also detaches itself on rollback.
    """
    from sqlalchemy import event

    from src.utils.storage import storage_service

    session = db.sync_session if hasattr(db, "sync_session") else db

    def _on_commit(_session) -> None:
        try:
            storage_service.delete_file(object_name)
        except Exception as exc:  # noqa: BLE001 - an orphan is not a failure
            logger.warning("could not delete previous persona avatar %s: %s",
                           object_name, exc)
        _detach()

    def _on_rollback(_session) -> None:
        _detach()

    def _detach() -> None:
        for name, fn in (("after_commit", _on_commit),
                         ("after_rollback", _on_rollback)):
            try:
                event.remove(session, name, fn)
            except Exception:  # noqa: BLE001 - already gone
                pass

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
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT},
                                     follow_redirects=True) as client:
            return await gravatar_if_exists(client, email)
    except Exception as exc:  # noqa: BLE001 - a picture never fails a save
        logger.warning("gravatar lookup failed for a persona update: %s", exc)
        return ""


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
    # to_dict serialises columns, and this is a property derived from
    # custom_metadata rather than a column of its own - so the recommendation
    # was computed, stored and never sent, and the badge had nothing to render.
    data["is_recommended"] = persona.is_recommended
    return data


def _resolve_avatar(persona_data) -> dict:
    """Decide a manually created persona's picture and record where it came from.

    The same precedence the extraction pipeline applies, so a persona a person
    types in and one the crawler found describe their picture in the same terms:
    an image the person supplied wins, a Gravatar is derived only when they gave
    an address and chose no image, and initials are drawn when they gave
    neither. Recorded rather than merely applied - a photograph and a coloured
    circle bearing someone's letters are not the same claim, and the URL alone
    does not say which it is.
    """
    from src.utils.fast_scraper import gravatar_url, initials_avatar  # noqa: F401

    supplied = (getattr(persona_data, "avatar_url", None) or "").strip()
    email = (getattr(persona_data, "email", None) or "").strip()
    if supplied:
        return {"avatar_url": supplied, "avatar_source": "custom", "email": email or None}
    if email and (derived := gravatar_url(email)):
        return {"avatar_url": derived, "avatar_source": "gravatar", "email": email}
    return {"avatar_url": initials_avatar(persona_data.name or ""),
            "avatar_source": "generated", "email": email or None}


@router.post("/{workspace_id}/personas", status_code=status.HTTP_201_CREATED, response_model=SuccessResponse[PersonaResponse])
@require_permissions("workspace.create", workspace_scoped=True)
@db_transaction_handler("create persona", auto_commit=True)
async def create_persona(
    workspace_id: str,
    persona_data: PersonaCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Create a new persona manually."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)
    
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
        **_resolve_avatar(persona_data),
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
        data=_persona_payload(persona),
        request=request,
        message="Persona created successfully"
    )


@router.put("/{workspace_id}/personas/{persona_id}", response_model=SuccessResponse[PersonaResponse])
@require_permissions("workspace.update", workspace_scoped=True)
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
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)
    
    # Fetch persona
    result = await db.execute(
        select(Persona).where(
            Persona.id == UUID(persona_id),
            Persona.workspace_id == workspace.id
        )
    )
    persona = result.scalar_one_or_none()
    
    if not persona:
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )
    
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

    # The picture follows from what was just changed. Saving an address and
    # leaving the avatar alone meant a person could type their email, press
    # update, and watch nothing happen - the field was stored, the Gravatar it
    # exists to derive was never asked for. Same precedence as everywhere else:
    # an image someone supplied wins, then a Gravatar, then initials, and a
    # photograph already found on the site is never replaced by a placeholder.
    if "avatar_url" in update_data or "email" in update_data:
        from src.utils.fast_scraper import initials_avatar

        supplied = (persona.avatar_url or "").strip()
        # Initials are ours, not a choice. They are stored inline as a data
        # URI, and an edit form returns whatever was in the field - so pressing
        # update marked our own placeholder as the user's custom image, which
        # then outranked the Gravatar the address beside it was meant to fetch.
        # Someone who types their email and sees nothing happen is watching a
        # picture they never chose beat one they did.
        if supplied.startswith("data:"):
            supplied = ""
        was_derived = (persona.avatar_source in (None, "", "gravatar", "generated")
                       or (persona.avatar_url or "").startswith("data:"))
        if "avatar_url" in update_data and supplied:
            persona.avatar_source = "custom"
        elif was_derived:
            email = (persona.email or "").strip()
            derived = await _gravatar_or_none(email) if email else ""
            if derived:
                persona.avatar_url, persona.avatar_source = derived, "gravatar"
            else:
                persona.avatar_url = initials_avatar(persona.name or "")
                persona.avatar_source = "generated"
    
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
    
    return success(
        data=_persona_payload(persona),
        request=request,
        message="Persona updated successfully"
    )


@router.delete("/{workspace_id}/personas/{persona_id}", status_code=status.HTTP_200_OK, response_model=SuccessResponse[GenericResponse])
@require_permissions("workspace.delete", workspace_scoped=True)
@db_transaction_handler("delete persona", auto_commit=True)
async def delete_persona(
    workspace_id: str,
    persona_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete a persona."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)
    
    # Fetch persona
    result = await db.execute(
        select(Persona).where(
            Persona.id == UUID(persona_id),
            Persona.workspace_id == workspace.id
        )
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
    
    return success(data={},request=request, message="Persona deleted successfully")


__all__ = ["router"]
