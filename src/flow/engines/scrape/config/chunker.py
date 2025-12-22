import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SlidingWindowChunker:
    """
    A utility class for splitting long text content into overlapping chunks.

    This is useful for processing large documents in smaller, manageable segments
    while maintaining some context between adjacent chunks through overlapping.
    """

    def __init__(self, window_size: int = 1000, step: int = 200):
        """
        Initialize the chunker with specific window and step sizes.

        Args:
            window_size (int): The number of words in each chunk.
            step (int): The number of words to advance the window for each subsequent chunk.
        """
        self.window_size = window_size
        self.step = step
        logger.debug(f"Initialized SlidingWindowChunker (window_size={window_size}, step={step})")

    def chunk(self, context: Any) -> List[Dict[str, Any]]:
        """
        Split the content of a document into overlapping chunks.

        Args:
            context (Any): An object (typically a LangChain Document) with:
                - page_content (str): The text content to be chunked.
                - metadata (dict): Metadata associated with the document.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each containing:
                - 'chunk' (str): The text segment.
                - 'metadata' (dict): The original document metadata.
        """
        content = getattr(context, 'page_content', '')
        metadata = getattr(context, 'metadata', {})

        if not content:
            logger.warning("Received empty content for chunking")
            return []

        # Split into words
        words = content.split()
        chunks = []

        logger.debug(f"Chunking content of length {len(words)} words")

        for i in range(0, len(words), self.step):
            chunk_words = words[i:i + self.window_size]
            if not chunk_words:
                continue
            
            chunks.append({
                'chunk': ' '.join(chunk_words),
                'metadata': metadata
            })

        logger.debug(f"Successfully created {len(chunks)} chunks")
        return chunks