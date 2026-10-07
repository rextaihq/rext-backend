from pydantic import BaseModel


class LibraryItemDeleted(BaseModel):
    """A keyword removed from the caller's library: its store key."""

    deleted_key: str
