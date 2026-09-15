"""Tunables for SERP-based competitor discovery.

Ported verbatim from the reference Colab notebook (competitor_discovery_agent.py) —
do not change these values without a concrete technical reason; they were validated
against known-good runs of the notebook.
"""

OPENAI_MODEL = "gpt-4o-mini"

MAX_INTERNAL_PAGES = 2  # extra pages beyond the homepage to scrape
MAX_QUERIES = 9  # total SERP queries (4 category + 5 brand — bumped from the
# notebook's 8 to fit the 5th brand-query pattern below)
MAX_ORGANIC_PER_QUERY = 10  # organic results pulled per query
MAX_LISTICLES_TO_MINE = 3  # how many "best X" / review pages to open and mine
MAX_CANDIDATES_TO_CLASSIFY = 24  # cap on how many candidate domains get LLM-classified
CLASSIFY_BATCH_SIZE = 8  # candidates per classification LLM call
CONCURRENCY = 10  # max concurrent HTTP requests
REQUEST_TIMEOUT = 10  # seconds per HTTP request
SERP_REQUEST_TIMEOUT = 30  # seconds for DataForSEO live search requests

SERP_LOCATION_CODE = 2840  # DataForSEO location code, 2840 = United States
SERP_LANGUAGE_CODE = "en"

# Domains that are never competitors themselves, but ARE worth mining for
# competitor names if they show up as "best X" / "alternatives" listicles.
LISTICLE_DOMAINS = {
    "g2.com",
    "capterra.com",
    "softwareadvice.com",
    "trustradius.com",
    "getapp.com",
    "producthunt.com",
    "saashub.com",
    "alternativeto.net",
}

# Domains to always exclude from the final competitor list.
BLOCKLIST_DOMAINS = {
    "wikipedia.org",
    "reddit.com",
    "youtube.com",
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "quora.com",
    "medium.com",
    "pinterest.com",
    "amazon.com",
    "apple.com",
    "google.com",
    "play.google.com",
    "apps.apple.com",
    "github.com",
    "crunchbase.com",
    "craft.co",
    "leadiq.com",
    "zoominfo.com",
    "pitchbook.com",
    "owler.com",
    "dnb.com",
    "datanyze.com",
    "stackshare.io",
    "postmake.io",
    "glassdoor.com",
    "indeed.com",
    "yelp.com",
    "tiktok.com",
}

# Deviation from the reference notebook: major website-building/CMS/e-commerce
# platform domains. The notebook's classification prompt has no concept of
# "the platform this business is built on/for" vs. a rival seller, so a
# WordPress/Shopify/etc.-focused business's own tooling can get misclassified
# as a "direct competitor" by the LLM. Blocked outright rather than left to
# classification, same mechanism as BLOCKLIST_DOMAINS above.
PLATFORM_BLOCKLIST_DOMAINS = {
    "wordpress.com",
    "wordpress.org",
    "shopify.com",
    "myshopify.com",
    "wix.com",
    "wixsite.com",
    "squarespace.com",
    "webflow.com",
    "weebly.com",
    "godaddy.com",
    "godaddysites.com",
    "elementor.com",
    "joomla.org",
    "drupal.org",
    "bigcommerce.com",
    "magento.com",
}

# --- Product requirements, not from the notebook ---
# The notebook has no concept of a minimum/maximum number of results to show
# a user, or of a confidence bar for what counts as "direct enough" to
# display. See pipeline.py::select_display_competitors.
MIN_DISPLAY_COMPETITORS = 5
MAX_DISPLAY_COMPETITORS = 9
DIRECT_CONFIDENCE_THRESHOLD = 0.75
