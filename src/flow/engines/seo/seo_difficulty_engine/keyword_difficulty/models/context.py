from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class CompetitorContext:
    keyword: str
    intent: str
    competitor: Dict[str, Any]
    serp_entry: Dict[str, Any]
    serp_results: List[Dict[str, Any]]
    serp_normalized: Dict[str, Any]
    competitors: List[Dict[str, Any]]
    scrape_doc: Optional[Dict[str, Any]]
