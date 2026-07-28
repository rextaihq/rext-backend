"""WordPress post-status normalization and internal status mapping."""


DEFAULT_WORDPRESS_POST_STATUS = "publish"
SELECTABLE_WORDPRESS_POST_STATUSES = frozenset({"publish", "draft", "pending"})
SUPPORTED_WORDPRESS_POST_STATUSES = frozenset(
    {
        *SELECTABLE_WORDPRESS_POST_STATUSES,
        "future",
        "private",
        "trash",
    }
)


def normalize_wordpress_post_status(
    status: str | None,
    *,
    default: str = DEFAULT_WORDPRESS_POST_STATUS,
) -> str:
    """Return the WordPress REST status value, accepting ``review`` as an alias."""
    normalized = (status or default).strip().lower()
    if normalized == "review":
        normalized = "pending"
    if normalized not in SUPPORTED_WORDPRESS_POST_STATUSES:
        supported = ", ".join(sorted(SUPPORTED_WORDPRESS_POST_STATUSES))
        raise ValueError(
            f"Unsupported WordPress post status '{status}'. "
            f"Expected one of: {supported}"
        )
    return normalized


def content_status_for_wordpress_status(status: str) -> str:
    """Map a WordPress post status to the corresponding Rext content status."""
    normalized = normalize_wordpress_post_status(status)
    return {
        "publish": "published",
        "pending": "review",
        "future": "scheduled",
        "draft": "draft",
        "private": "draft",
        "trash": "trashed",
    }[normalized]
