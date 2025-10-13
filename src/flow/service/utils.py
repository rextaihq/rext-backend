def get_progress_percent(stage: str) -> int:
    mapping = {
        "FetchUser": 5,
        "FetchWorkspace": 10,
        "FetchTopic": 20,
        "WebContext": 35,
        "KnowledgeContext": 55,
        "ScrapeContent": 70,
        "RerankContent": 85,
        "BlogGeneration": 95,
        "Completed": 100,
    }
    return mapping.get(stage, 0)
