import logging
from typing import Optional, List, Union
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from crawl4ai import CacheMode
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from src.flow.engines.scrape.config.markdown_generator import MarkdownGeneratorFactory
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)

class CrawlerConfiguration(MarkdownGeneratorFactory):
    """
    Handles the configuration for the Crawl4AI browser and crawler.

    This class provides methods to generate optimized configurations for:
    - Browser settings (headless mode, browser type, etc.)
    - Crawler run settings (content extraction, link scoring, caching, etc.)
    """

    def __init__(self, query: str):
        """
        Initialize the configuration with a search query.

        Args:
            query (str): The search query used for link scoring and content relevance.
        """
        super().__init__(query=query)
        logger.debug(f"Initialized CrawlerConfiguration for query: '{query}'")

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
        )

    def get_run_config(self, cache_mode: CacheMode = CacheMode.ENABLED) -> CrawlerRunConfig:
        """
        Generate the run configuration for the crawler.

        This includes settings for content extraction, markdown generation,
        caching, and link scoring based on the initial query.

        Returns:
            CrawlerRunConfig: The configured crawler run settings.
        """
        logger.debug(f"Generating crawler run config with cache_mode={cache_mode}")
        return CrawlerRunConfig(
            word_count_threshold=200,
            markdown_generator=self.get_markdown_generator(),
            remove_forms=True, # Optimization: remove forms
            prettiify=True,
            parser_type="lxml",
            excluded_tags=[ # Scripts & styles
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
            "base"
            ],
            scraping_strategy=LXMLWebScrapingStrategy(),
            # # --- Navigation & Timing ---
            # wait_until="domcontentloaded",
            exclude_external_links=True,
            # Block entire domains
            exclude_social_media_domains=["facebook.com", "twitter.com","youtube.com","instagram.com","tiktok.com","linkedin.com","pinterest.com","reddit.com","telegram.org","whatsapp.com","signal.org","viber.com","snapchat.com"],

            # Media filtering
            exclude_external_images=True,
            exclude_social_media_links=True,
            simulate_user =True,
            magic=True,
            adjust_viewport_to_content=True,
            cache_mode=cache_mode,
            score_links=True,
            # link_preview_config=self._get_link_score(
            #     threshold=0.3,
            #     max_links=10,
            #     verbose=False
            # )
        )