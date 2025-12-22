import logging
from typing import List, Dict, Any
from sentence_transformers import util
from src.utils.embedding import get_embedding

logger = logging.getLogger(__name__)

class SemanticSimilarityExtractor:
    """
    A utility class for extracting relevant text chunks based on semantic similarity.

    It uses an embedding model to compare a user query against a list of text chunks
     and filters them based on a cosine similarity threshold.
    """

    def __init__(self, query: str, threshold: float = 0.3):
        """
        Initialize the extractor with a query and similarity threshold.

        Args:
            query (str): The user query to compare against chunks.
            threshold (float): The minimum cosine similarity score for a chunk to be considered relevant.
        """
        self.query = query
        self.threshold = threshold
        self.model = get_embedding()
        logger.debug(f"Initialized SemanticSimilarityExtractor (threshold={threshold})")

    def find_relevant_chunks(self, chunk_dicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify and score chunks that are semantically similar to the query.

        Args:
            chunk_dicts (List[Dict[str, Any]]): A list of dictionaries, each containing:
                - 'chunk' (str): The text content.
                - 'metadata' (dict): Associated metadata.

        Returns:
            List[Dict[str, Any]]: A list of relevant chunks, sorted by score, each containing:
                - 'chunk' (str): The text content.
                - 'metadata' (dict): Associated metadata.
                - 'score' (float): The cosine similarity score.
        """
        if not chunk_dicts:
            logger.warning("No chunks provided for similarity extraction")
            return []

        chunks = [c['chunk'] for c in chunk_dicts]
        logger.debug(f"Computing embeddings for {len(chunks)} chunks")

        try:
            # Compute embeddings using the provided embedding model (e.g., Ollama)
            query_emb = self.model.embed_query(self.query)
            chunk_embs = self.model.embed_documents(chunks)

            # Compute cosine similarities
            # Note: util.cos_sim expects tensors or arrays. 
            # If get_embedding returns a LangChain embedding model, we might need to convert to tensors.
            similarities = util.cos_sim(query_emb, chunk_embs).squeeze(0)

            # Filter by threshold and build result list
            relevant = [
                {
                    'chunk': chunk_dicts[i]['chunk'],
                    'metadata': chunk_dicts[i]['metadata'],
                    'score': float(similarities[i])
                }
                for i in range(len(chunks))
                if similarities[i] > self.threshold
            ]

            # Sort by highest similarity
            relevant.sort(key=lambda x: x['score'], reverse=True)
            logger.info(f"Found {len(relevant)} relevant chunks out of {len(chunks)}")
            return relevant

        except Exception as e:
            logger.exception(f"Error during semantic similarity computation: {str(e)}")
            return []