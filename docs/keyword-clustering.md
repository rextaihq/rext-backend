## Keyword Clustering (SERP -> Clusters)

Pipeline implemented in `src/services/keyword_clustering_service.py`:

1. Extract keyword candidates from `serp_normalized` (titles/snippets/topics/questions)
2. Filter to seed intent (best-effort heuristic intent inference when per-keyword intent is missing)
3. Optionally enrich missing `search_volume` and `keyword_difficulty` with DataForSEO
4. Optionally filter to high-volume / low-KD keywords when metrics exist
5. Create embeddings (`text-embedding-3-small`)
6. Build a cosine semantic similarity matrix and cosine distance matrix
7. Cluster with HDBSCAN and validate; fallback to Agglomerative if HDBSCAN is unavailable or unstable
8. Return final clusters sorted by total score

### Passing Seed Intent

`keyword_clustering_node` uses:

- `serp_payload.intent` (if you set it from UI/LLM) No its not correct approch. do not fetch here.
- else `seo_result.intent_type`
- else `seo_result.serp_backlinks.main_intent` (DataForSEO)

### Thresholds / Config Overrides

You can override knobs by passing `serp_payload.keyword_clustering_config`:

```json
{
  "min_seed_similarity": 0.35,
  "min_cluster_size": 2,
  "min_search_volume": 100,
  "max_keyword_difficulty": 25,
  "require_metrics": false,
  "enable_dataforseo_metrics": false,
  "location_name": "Pakistan",
  "language_code": "en"
}
```

Notes:
- If `require_metrics=true`, keywords without `search_volume`/`keyword_difficulty` are dropped after optional enrichment.
- If HDBSCAN cannot be imported, clustering falls back automatically.
- Metric enrichment uses `serp_payload.location_code` or `serp_payload.country` plus `serp_payload.language_code` by default, unless location/language are overridden.
- DataForSEO accepts either `location_name` or `location_code`, and either `language_code` or `language_name`.
- DataForSEO enrichment requires `DATAFORSEO_BACKLINKS_URL` and `DATAFORSEO_AUTH_HEADER`.
