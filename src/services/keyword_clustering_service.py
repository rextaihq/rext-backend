import logging
import numpy as np
from typing import List, Dict, Any
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

from src.utils.embedding import get_embedding
from src.flow.states.seo_state import KeywordCluster

logger = logging.getLogger(__name__)

class KeywordClusteringService:
    """
    Service for grouping keywords into semantic clusters using embeddings.
    """
    
    def __init__(self, distance_threshold: float = 0.45):
        """
        Initialize the clustering service.
        
        Args:
            distance_threshold: The linkage distance threshold. 
                               Lower value = more granular clusters.
                               Standard for OpenAI text-embedding-3-small is 0.2 - 0.3.
        """
        self.distance_threshold = distance_threshold
        self.embeddings_model = get_embedding()
        
    async def cluster_keywords(self, keywords_data: List[Dict[str, Any]]) -> List[KeywordCluster]:
        """
        Clusters a list of keyword objects into semantic groups.
        
        Args:
            keywords_data: List of dicts containing 'keyword' and 'score'
            
        Returns:
            List of KeywordCluster objects.
        """
        if not keywords_data:
            return []
            
        if len(keywords_data) == 1:
            return [self._format_cluster([keywords_data[0]])]

        try:
            # 1. Extract raw keyword strings
            keyword_texts = [kw["keyword"] for kw in keywords_data]
            
            # 2. Generate embeddings
            # OpenAI embeddings are already normalized for cosine similarity
            embeddings = await self.embeddings_model.aembed_documents(keyword_texts)
            embeddings_np = np.array(embeddings)
            
            # 3. Perform Agglomerative Clustering
            # We use 'cosine' affinity and 'average' linkage for stable SEO clusters
            clustering_model = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=self.distance_threshold,
                metric='cosine',
                linkage='average'
            )
            
            cluster_ids = clustering_model.fit_predict(embeddings_np)
            
            # 4. Group keywords by cluster ID
            groups = {}
            for idx, cluster_id in enumerate(cluster_ids):
                if cluster_id not in groups:
                    groups[cluster_id] = []
                groups[cluster_id].append(keywords_data[idx])
                
            # 5. Format and name each cluster
            clusters = []
            for group_keywords in groups.values():
                clusters.append(self._format_cluster(group_keywords))
                
            # Sort clusters by total score descending
            clusters.sort(key=lambda x: x["total_score"], reverse=True)
            
            logger.info(f"Successfully clustered {len(keywords_data)} keywords into {len(clusters)} groups")
            return clusters
            
        except Exception as e:
            logger.error(f"Error during keyword clustering: {e}")
            # Fallback: Treat all keywords as one cluster if clustering fails
            return [self._format_cluster(keywords_data)]

    def _format_cluster(self, group_keywords: List[Dict[str, Any]]) -> KeywordCluster:
        """
        Identifies the centroid (best keyword) and formats the cluster object.
        """
        # Sort by score within the group to pick the "Name" (Centroid replacement)
        sorted_group = sorted(group_keywords, key=lambda x: x.get("score", 0), reverse=True)
        
        cluster_name = sorted_group[0]["keyword"]
        total_score = sum(kw.get("score", 0) for kw in group_keywords)
        
        return {
            "cluster_name": cluster_name,
            "keywords": sorted_group,
            "total_score": round(total_score, 2),
            "main_intent": sorted_group[0].get("intent") # Inherit intent from top keyword if available
        }
