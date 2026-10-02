import logging
from typing import Any, Dict, List

import numpy as np

from src.utils.embedding import get_embedding

logger = logging.getLogger(__name__)


class SemanticSimilarityExtractor:
    """
    A utility class for extracting relevant text chunks based on semantic similarity.

    It uses an embedding model to compare a user query against a list of text chunks
     and filters them based on a cosine similarity threshold.
    """

    def __init__(self, query: str, threshold: float = 0.3, token_threshold: int = 30000):
        """
        Initialize the extractor with a query and similarity threshold.

        Args:
            query (str): The user query to compare against chunks.
            threshold (float): The minimum cosine similarity score for a chunk to be considered relevant.
        """
        self.query = query
        self.threshold = threshold
        self.token_threshold = token_threshold
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

        chunks = [c["chunk"] for c in chunk_dicts]

        # Estimate tokens and limit chunks to stay under self.token_threshold
        limited_chunks = []
        current_tokens = 0
        for chunk in chunks:
            # Rough estimate: 1 word ~= 1.33 tokens
            estimated_tokens = len(chunk.split()) * 1.33
            if current_tokens + estimated_tokens > self.token_threshold:
                logger.warning(
                    f"Reached token threshold ({self.token_threshold}). Truncating chunks for embedding."
                )
                break
            limited_chunks.append(chunk)
            current_tokens += estimated_tokens

        logger.debug(
            f"Computing embeddings for {len(limited_chunks)} chunks (estimated {int(current_tokens)} tokens)"
        )

        try:
            # Compute embeddings using the provided embedding model
            query_emb = self.model.embed_query(self.query)
            chunk_embs = self.model.embed_documents(limited_chunks)

            # Compute cosine similarities using numpy
            query_vec = np.array(query_emb)
            chunk_vecs = np.array(chunk_embs)
            query_norm = np.linalg.norm(query_vec)
            chunk_norms = np.linalg.norm(chunk_vecs, axis=1)
            denom = query_norm * chunk_norms
            denom[denom == 0] = 1.0
            similarities = np.dot(chunk_vecs, query_vec) / denom

            # Filter by threshold and build result list
            relevant = [
                {
                    "chunk": chunk_dicts[i]["chunk"],
                    "metadata": chunk_dicts[i]["metadata"],
                    "score": float(similarities[i]),
                }
                for i in range(len(limited_chunks))
                if similarities[i] > self.threshold
            ]

            # Sort by highest similarity
            relevant.sort(key=lambda x: x["score"], reverse=True)
            logger.info(f"Found {len(relevant)} relevant chunks out of {len(chunks)}")
            return relevant

        except Exception as e:
            logger.exception(f"Error during semantic similarity computation: {str(e)}")
            return []
