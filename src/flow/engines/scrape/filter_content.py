import logging
from typing import Dict, Any, List
from src.flow.states.wrext import WREXT
from src.flow.engines.scrape.config.chunker import SlidingWindowChunker
from src.flow.engines.scrape.config.sementic_filter import SemanticSimilarityExtractor

logger = logging.getLogger(__name__)

def filter_relevant_content(
    state: WREXT,
    threshold: float = 0.3,
    window_size: int = 1000,
    step: int = 200
) -> Dict[str, Any]:
    """
    Filters scraped content to identify and return only the most relevant chunks based on the query.

    This function:
    1. Retrieves the search query and scraped documents from the state.
    2. Chunks the scraped documents using a sliding window approach.
    3. Filters chunks by minimum word count (content already cleaned in scrape_content.py).
    4. Uses semantic similarity to score and filter chunks against the query.
    5. Returns the top relevant chunks sorted by their similarity score.

    Args:
        state (WREXT): The current state containing 'scrape_context' and 'serp_payload'.
        threshold (float): The minimum similarity score for a chunk to be considered relevant.
        window_size (int): The number of words in each sliding window chunk.
        step (int): The number of words to advance the window for each subsequent chunk.

    Returns:
        Dict[str, Any]: A dictionary containing 'relevant_context', a list of relevant chunks with metadata and scores.
    """
    logger.info("Starting content filtering process")
    
    scrape_context = state.get('scrape_context', {})
    serp_payload = state.get('serp_payload', {})
    query = serp_payload.get('query', '')
    
    # Extract documents list from scrape_context dict
    documents = scrape_context.get('documents', [])

    if not documents:
        logger.warning("No documents found in scrape_context - skipping filtering")
        return {'relevant_context': []}
    
    if not query:
        logger.warning("No query found in serp_payload - cannot perform semantic filtering")
        return {'relevant_context': []}

    logger.debug(f"Filtering content for query: '{query}' using threshold: {threshold}")

    chunker = SlidingWindowChunker(window_size=window_size, step=step)

    extractor = SemanticSimilarityExtractor(query=query, threshold=threshold)
    
    from concurrent.futures import ThreadPoolExecutor

    def process_document(doc_data):
        # doc_data is a DocumentScrapeData dict with 'document' key
        doc = doc_data.get('document')
        if not doc:
            return []
        
        doc_chunks = chunker.chunk(doc)
        if not doc_chunks:
            return []
        
        # Filter chunks with at least 30 words (content already cleaned in scrape_content.py)
        return [
            {'chunk': c['chunk'], 'metadata': c['metadata']}
            for c in doc_chunks
            if len(c['chunk'].split()) >= 30
        ]

    all_chunks = []
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(process_document, documents))
        for res in results:
            all_chunks.extend(res)

    if not all_chunks:
        logger.info("No meaningful chunks extracted from the scraped content")
        return {'relevant_context': []}

    logger.debug(f"Extracted {len(all_chunks)} chunks for semantic analysis")

    try:
        relevant_data = extractor.find_relevant_chunks(all_chunks)
        logger.info(f"Successfully identified {len(relevant_data)} relevant chunks")
    except Exception as e:
        logger.exception(f"Error during semantic similarity extraction: {str(e)}")
        return {'relevant_context': []}

    return {
        "relevant_context": relevant_data
    }