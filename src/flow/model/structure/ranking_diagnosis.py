from typing import List
from pydantic import BaseModel, Field


class RankingDiagnosisExplanation(BaseModel):
    """
    LLM output for Module 5 (AI Diagnosis). The model narrates ONLY the
    pre-verified signals it is given — it does not have tools or retrieval
    access, so it cannot introduce facts beyond what's in its prompt.
    """

    summary: str = Field(
        description=(
            "One or two sentences stating what changed (e.g. 'Ranking dropped "
            "by 5 positions over the last 28 days.'). State only the direction "
            "and magnitude given in the input data — do not speculate about "
            "causes here."
        )
    )
    reasons: List[str] = Field(
        description=(
            "Short, clear restatements of the supplied signals ONLY — one per "
            "triggered signal, no more, no fewer. Do not add any reason not "
            "present in the input. If no signals were supplied, return an "
            "empty list."
        )
    )
