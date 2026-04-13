from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Project-wide default for LLM structured outputs: reject unknown fields."""

    model_config = ConfigDict(extra="forbid")

