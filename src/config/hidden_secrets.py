"""Settings objects that print without their secrets.

pydantic prints every field with its value (``repr``, ``str``), so anything that turns a
settings object into text would carry the keys with it: a log line, an error message that
quotes the object, a crash report that records a frame's local variables (Sentry does by
default). The mixin keeps every field's name and hides the value of a secret one, and a
password inside an address such as a database URI, in its user part or its query.
"""

import re
from typing import Any, Iterator, Optional, Tuple

# A field whose name says it holds a secret. Only string values are hidden, so a number
# such as ACCESS_TOKEN_EXPIRE_MINUTES still prints.
SECRET_NAME = re.compile(r"KEY|SECRET|PASSWORD|TOKEN|DSN|CREDENTIAL|PRIVATE", re.IGNORECASE)
# The password in "scheme://user:password@host".
ADDRESS_PASSWORD = re.compile(r"(?<=://)([^/@\s:]*):([^/@\s]*)@")
# A secret passed as a query parameter: "...?password=...", "&sslpassword=...", "&token=...".
QUERY_SECRET = re.compile(
    r"([?&;](?:[a-z_]*password|passwd|pwd|pass|secret|token|[a-z_]*key)=)([^&#;\s]*)",
    re.IGNORECASE,
)
HIDDEN = "**********"


def hide_secret(name: str, value: Any) -> Any:
    """The value as it may be printed."""
    if not isinstance(value, str) or not value:
        return value
    if SECRET_NAME.search(name):
        return HIDDEN
    value = ADDRESS_PASSWORD.sub(lambda match: f"{match.group(1)}:{HIDDEN}@", value)
    return QUERY_SECRET.sub(lambda match: f"{match.group(1)}{HIDDEN}", value)


class HidesSecrets:
    """Put first in a pydantic settings class's bases: its ``repr`` and ``str`` then hide
    secret values."""

    def __repr_args__(self) -> Iterator[Tuple[Optional[str], Any]]:
        for name, value in super().__repr_args__():  # type: ignore[misc]
            yield name, hide_secret(name or "", value)
