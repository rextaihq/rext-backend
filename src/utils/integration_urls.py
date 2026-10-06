"""The check every customer-given integration address passes before the API stores or uses it."""

from src.api.middleware.exceptions import RextValidationException
from src.utils.logger import logger
from src.utils.url_validator import (
    InvalidURLError,
    SSRFValidationError,
    UnresolvableHostError,
    ensure_public_urls,
)

PRIVATE_ADDRESS_MESSAGE = (
    "The site's address points to a private or reserved network. Use the site's public address."
)
INVALID_ADDRESS_MESSAGE = "The site's address is not a valid URL. Check it and try again."
UNKNOWN_HOST_MESSAGE = "The site's address could not be found. Check it and try again."


async def ensure_public_site_urls(*urls: object) -> None:
    """Refuse, with an error the dashboard can show, a site URL or API endpoint that
    leads to a private or reserved address (the API's own network, Redis, cloud
    metadata). Empty and blank values are skipped; a value that is not a string
    (config_json is free-form) is not a valid address."""
    if any(url is not None and not isinstance(url, str) for url in urls):
        raise RextValidationException(message=INVALID_ADDRESS_MESSAGE)
    try:
        await ensure_public_urls(*urls)
    except InvalidURLError as exc:
        # No scheme, an unsupported one, or no host: refused, but not because of
        # where it leads.
        logger.info(f"Integration address is not a valid URL: {exc}")
        raise RextValidationException(message=INVALID_ADDRESS_MESSAGE) from None
    except UnresolvableHostError as exc:
        logger.info(f"Integration address not found: {exc}")
        raise RextValidationException(message=UNKNOWN_HOST_MESSAGE) from None
    except SSRFValidationError as exc:
        logger.warning(f"Integration address refused: {exc}")
        raise RextValidationException(message=PRIVATE_ADDRESS_MESSAGE) from None
    except ValueError as exc:
        # urlparse raises a plain ValueError for an address it cannot parse,
        # such as "http://[invalid".
        logger.info(f"Integration address not parsed: {exc}")
        raise RextValidationException(message=INVALID_ADDRESS_MESSAGE) from None
