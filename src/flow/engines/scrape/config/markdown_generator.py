import logging
from typing import Optional, Union
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai import LinkPreviewConfig
from crawl4ai.content_filter_strategy import BM25ContentFilter

logger = logging.getLogger(__name__)

class MarkdownGeneratorFactory:
    """
    Factory class for creating and configuring markdown generators and content filters.

    This class provides methods to:
    - Create a DefaultMarkdownGenerator with BM25 content filtering.
    - Configure link preview and scoring based on a user query.
    """

    def __init__(self, query: str):
        """
        Initialize the factory with a search query.

        Args:
            query (str): The search query used for content filtering and link scoring.
        """
        self.query = query
        logger.debug(f"Initialized MarkdownGeneratorFactory for query: '{query}'")

    def get_markdown_generator(self) -> DefaultMarkdownGenerator:
        """
        Create a configured DefaultMarkdownGenerator.

        The generator uses a BM25 filter to prioritize content relevant to the query.

        Returns:
            DefaultMarkdownGenerator: The configured markdown generator.
        """
        logger.debug("Creating DefaultMarkdownGenerator with BM25 filter")
        return DefaultMarkdownGenerator(
            content_filter=self._get_bm25_filter(),
            content_source="cleaned_html",
            options={
                "ignore_links": False,
                "ignore_images": True,
                "body_width": 0,
                "escape_html": False
            },
        )

    def _get_bm25_filter(self, threshold: float = 0.5) -> BM25ContentFilter:
        """
        Create a BM25 content filter based on the user query.

        Args:
            threshold (float): The BM25 score threshold for content relevance.

        Returns:
            BM25ContentFilter: The configured content filter.
        """
        logger.debug(f"Creating BM25ContentFilter with threshold: {threshold}")
        return BM25ContentFilter(
            user_query=self.query,
            bm25_threshold=threshold
        )

    def _get_link_score(
        self,
        threshold: float = 0.3,
        max_links: int = 100,
        concurrency: int = 20,
        timeout: int = 10,
        verbose: bool = False,
    ) -> LinkPreviewConfig:
        """
        Configure link preview and scoring settings.

        Args:
            threshold (float): The minimum score for a link to be included.
            max_links (int): The maximum number of links to process.
            concurrency (int): The number of concurrent link processing tasks.
            timeout (int): The timeout in seconds for each link processing task.
            verbose (bool): Whether to enable verbose logging for link processing.

        Returns:
            LinkPreviewConfig: The configured link preview settings.
        """
        logger.debug(f"Creating LinkPreviewConfig with threshold: {threshold}")
        return LinkPreviewConfig(
            include_internal=True,
            include_external=True,
            max_links=max_links,
            concurrency=concurrency,
            timeout=timeout,
            query=self.query,
            score_threshold=threshold,
            verbose=verbose
        )