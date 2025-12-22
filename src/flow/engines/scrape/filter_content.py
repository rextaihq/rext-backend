import logging
from typing import Dict, Any, List
from src.flow.states.wrext import WREXT
from src.flow.engines.scrape.config.chunker import SlidingWindowChunker
from src.flow.engines.scrape.config.sementic_filter import SemanticSimilarityExtractor
from src.flow.engines.scrape.config.clean_content import clean_content

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
    1. Retrieves the search query and scraped context from the state.
    2. Chunks the scraped documents using a sliding window approach.
    3. Cleans each chunk to remove excessive noise.
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
    
    scrape_context = state.get('scrape_context', [])
    serp_payload = state.get('serp_payload', {})
    query = serp_payload.get('query', '')

    if not scrape_context:
        logger.warning("No scrape_context found in state - skipping filtering")
        return {'relevant_context': []}
    
    if not query:
        logger.warning("No query found in serp_payload - cannot perform semantic filtering")
        return {'relevant_context': []}

    logger.debug(f"Filtering content for query: '{query}' using threshold: {threshold}")

    chunker = SlidingWindowChunker(window_size=window_size, step=step)

    extractor = SemanticSimilarityExtractor(query=query, threshold=threshold)
    
    all_chunks = []
    for idx, doc in enumerate(scrape_context):
        # doc is a Document object
        doc_chunks = chunker.chunk(doc)
        
        if not doc_chunks:
            continue

        # Clean chunks and filter by length
        cleaned_doc_chunks = []
        for c in doc_chunks:
            cleaned_text = clean_content(c['chunk'])
            
            # Only keep chunks with a minimum word count to ensure meaningful context
            if len(cleaned_text.split()) >= 30:
                cleaned_doc_chunks.append({
                    'chunk': cleaned_text,
                    'metadata': c['metadata']
                })
        
        all_chunks.extend(cleaned_doc_chunks)

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

    return {'relevant_context': relevant_data}