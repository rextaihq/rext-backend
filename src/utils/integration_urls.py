"""The check every customer-given integration address passes before the API stores or uses it."""

from src.api.middleware.exceptions import RextValidationException
from src.utils.logger import logger
from src.utils.url_validator import SSRFValidationError, ensure_public_urls

PRIVATE_ADDRESS_MESSAGE = (
    "The site's address points to a private or reserved network. Use the site's public address."
)
INVALID_ADDRESS_MESSAGE = "The site's address is not a valid URL. Check it and try again."


async def ensure_public_site_urls(*urls: str | None) -> None:
    """Refuse, with an error the dashboard can show, a site URL or API endpoint that
    leads to a private or reserved address (the API's own network, Redis, cloud
    metadata). Empty values are skipped."""
    try:
        await ensure_public_urls(*urls)
    except SSRFValidationError as exc:
        logger.warning(f"Integration address refused: {exc}")
        raise RextValidationException(message=PRIVATE_ADDRESS_MESSAGE) from None
    except ValueError as exc:
        # urlparse raises a plain ValueError for an address it cannot parse,
        # such as "http://[invalid".
        logger.info(f"Integration address not parsed: {exc}")
        raise RextValidationException(message=INVALID_ADDRESS_MESSAGE) from None
