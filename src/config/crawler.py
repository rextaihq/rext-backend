import logging
import os

from crawl4ai import CacheMode
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy

logger = logging.getLogger(__name__)


class CrawlerConfiguration:
    """
    Handles the configuration for the Crawl4AI browser and crawler.

    This class provides methods to generate optimized configurations for:
    - Browser settings (headless mode, browser type, etc.)
    - Crawler run settings (content extraction, link scoring, caching, etc.)
    """

    def get_browser_config(
        self,
        headless: bool = True,
        ignore_https_errors: bool = True,
        verbose: bool = os.getenv("DEBUG", "false").lower() == "true",
    ) -> BrowserConfig:
        """
        Generate the browser configuration for scraping.

        Args:
            headless (bool): Whether to run the browser in headless mode.
            user_data_dir (Optional[str]): Path to the user data directory for persistent sessions.
            ignore_https_errors (bool): Whether to ignore SSL certificate errors.
            verbose (bool): Whether to enable verbose logging for the browser.

        Returns:
            BrowserConfig: The configured browser settings.
        """
        logger.debug(f"Generating browser config (headless={headless})")
        return BrowserConfig(
            browser_type="chromium",
            channel="chromium",
            chrome_channel="chromium",
            headless=headless,
            browser_mode="dedicated",
            use_managed_browser=False,
            java_script_enabled=True,
            ignore_https_errors=ignore_https_errors,
            text_mode=False,
            # playwright-stealth patches (navigator.webdriver, plugins, etc.) — a
            # site fronted by Cloudflare/PerimeterX/Akamai serves a challenge page
            # instead of real content to a fingerprinted headless browser, which
            # yields empty/near-empty markdown and silently kills persona/brand
            # extraction downstream. This is a one-shot page patch, not a runtime
            # behavior simulation, so it carries none of the hang risk called out
            # below for `magic`/`simulate_user`.
            enable_stealth=True,
        )

    def get_run_config(
        self,
        cache_mode: CacheMode = CacheMode.BYPASS,
        aggressive: bool = False,
    ) -> CrawlerRunConfig:
        """
        Generate the run configuration for the crawler.

        This includes settings for content extraction, markdown generation,
        caching, and link scoring based on the initial query.

        Args:
            cache_mode: Crawl4AI cache mode.
            aggressive: Use a stronger anti-bot/anti-cookie-wall pass. Reserved
                for the fallback retry in ``web_page_scraper`` when a first,
                cheap pass looks blocked — never used as the default because
                ``simulate_user``/``magic`` add real (bounded, but nonzero)
                latency and were previously observed to hang on some
                bot-protected sites when left on unconditionally.

        Returns:
            CrawlerRunConfig: The configured crawler run settings.
        """
        logger.debug(
            f"Generating crawler run config with cache_mode={cache_mode}, aggressive={aggressive}"
        )
        return CrawlerRunConfig(
            word_count_threshold=200,
            remove_forms=True,  # Optimization: remove forms
            prettiify=True,  # NOTE: Intentional spelling — matches crawl4ai's parameter name
            parser_type="lxml",
            excluded_tags=[  # Scripts & styles
                "script",
                "style",
                "noscript",
                # Embedded / non-text media
                "iframe",
                "object",
                "embed",
                "canvas",
                "svg",
                "math",
                # Audio / video
                "video",
                "audio",
                "source",
                "track",
                # Form elements (no SEO value)
                "form",
                "input",
                "textarea",
                "button",
                "select",
                "option",
                "label",
                "fieldset",
                "legend",
                # UI / interactive only
                "dialog",
                "details",
                "summary",
                "menu",
                "menuitem",
                # Ruby / annotation (rare SEO use)
                "ruby",
                "rt",
                "rp",
                # Misc non-content
                "param",
                "map",
                "area",
                "base",
            ],
            scraping_strategy=LXMLWebScrapingStrategy(),
            # --- Navigation & Timing ---
            page_timeout=45000
            if aggressive
            else 30000,  # hard limit per page — prevents infinite hang
            mean_delay=0.5,
            max_range=1.0,
            # IMPORTANT — do NOT set exclude_external_links / exclude_social_media_links
            # to True. Crawl4AI implements both by finding matching <a> tags and calling
            # `link.getparent().remove(link)` — that deletes the whole element, VISIBLE
            # TEXT INCLUDED, not just the href. Founder/author bylines are routinely
            # hyperlinked to an external personal site or a LinkedIn/Twitter profile
            # (both linkedin.com and twitter.com/x.com are in crawl4ai's own
            # SOCIAL_MEDIA_DOMAINS list) — with either flag on, "Written by [Jane
            # Doe](linkedin.com/in/janedoe)" is deleted outright and the LLM never sees
            # the name. Confirmed directly on nextlyhq.com: the footer credit
            # "Built by [Mobeen Abdullah](mobeenabdullah.com) at [Revnix](revnix.com)"
            # came back as "Built by at" with both names stripped, purely because both
            # links pointed off-domain. Leaving both flags off keeps this text; any
            # nav/social-icon noise it reintroduces is already filtered out by the
            # extraction prompt's own persona/competitor rules.
            exclude_external_links=False,
            exclude_social_media_domains=[
                "facebook.com",
                "twitter.com",
                "youtube.com",
                "instagram.com",
                "tiktok.com",
                "linkedin.com",
                "pinterest.com",
                "reddit.com",
                "telegram.org",
                "whatsapp.com",
                "signal.org",
                "viber.com",
                "snapchat.com",
            ],
            # Media filtering
            exclude_external_images=True,
            exclude_social_media_links=False,
            # Dismiss cookie-consent banners / GDPR modals / popups before the page
            # is read. Many EU-compliant sites (via OneTrust, Cookiebot, Osano,
            # Didomi, etc.) render the real page behind a full-screen consent
            # overlay; crawl4ai's built-in `remove_overlay_elements` JS pass
            # strips exactly these elements from the live DOM before extraction.
            # This is a single bounded JS call — not a behavioral simulation —
            # so it's always safe to leave on.
            remove_overlay_elements=True,
            # Patches navigator.webdriver / plugins so basic bot-detection
            # (Cloudflare, PerimeterX, Akamai) doesn't serve a JS challenge page
            # instead of real content. A one-shot init script, not a runtime
            # loop, so — unlike `simulate_user`/`magic` below — it carries no
            # hang risk and is safe to always enable.
            override_navigator=True,
            # Give overlay-removal + client-side hydration (React/Next.js sites
            # that render team/author bios after mount) a moment to settle
            # before the DOM is read.
            delay_before_return_html=1.5 if aggressive else 1.0,
            # `simulate_user`/`magic` add light mouse/keyboard interaction and a
            # randomized user agent. They were previously observed to hang on
            # some bot-protected sites when left on unconditionally, so they're
            # reserved for the bounded fallback retry (`aggressive=True`) in
            # `web_page_scraper`, never the default first pass.
            simulate_user=aggressive,
            magic=aggressive,
            adjust_viewport_to_content=False,  # can block on infinite-scroll pages
            cache_mode=cache_mode,
            score_links=False,  # fires extra HTTP HEAD requests per link
            # remove_overlay_elements=True, # also remove other blocking popups (newsletter, modals)
        )
