from abc import ABC, abstractmethod
from ..models.context import CompetitorContext

class DifficultyComponent(ABC):
    name: str

    @abstractmethod
    def score(self, ctx: CompetitorContext) -> float:
        """Must return normalized score between 0–1"""
        pass
