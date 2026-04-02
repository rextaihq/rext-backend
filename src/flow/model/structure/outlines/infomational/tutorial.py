from typing import List, Optional, Literal
from pydantic import BaseModel, Field, conlist


class CodeSnippet(BaseModel):
    """A suggested code block or mathematical equation/expression."""
    language: str = Field(description="Programming language or format (e.g., 'python', 'json', 'latex').")
    description: str = Field(description="Explanation of what this snippet does or teaches.")
    difficulty: Literal["Easy", "Medium", "Hard"] = "Easy"


class TutorialStep(BaseModel):
    """A practical step within the tutorial."""
    title: str = Field(description="Tutorial step heading.")
    description: str = Field(description="Practical instructions for the user.")
    code_suggestions: Optional[List[CodeSnippet]] = Field(default_factory=list, description="Associated code snippets or technical diagrams.")


class TutorialSection(BaseModel):
    heading: str = Field(description="Section heading.")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="Goal of this section in the learning curve.")
    steps: conlist(TutorialStep, min_length=1, max_length=10)


class TutorialOutline(BaseModel):
    title: str = Field(description="SEO-optimized tutorial title starting with 'How to' or including focus keyphrase.")
    slug_suggestion: str = Field(
        pattern=r"^[a-z0-9-]+$",
        description="Suggested URL slug."
    )
    brief: str = Field(description="The primary learning objective and prerequisite knowledge.")
    
    # Prerequisite Strategy
    focus_keyphrase: str = Field(
        description="The primary technical skill or concept being taught."
    )
    keywords_to_include: conlist(str, min_length=2)
    difficulty: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"
    environment_setup: Optional[str] = Field(description="Necessary tools, software, or credentials.")
    
    # Structure
    sections: conlist(TutorialSection, min_length=3, max_length=10)
    
    # Images/Diagrams Planning
    image_suggestions: List[str] = Field(
        description="Suggested screenshots or technical diagrams (min 2)."
    )
    
    # Links Planning
    link_suggestions: List[str] = Field(
        description="Related documentation or prerequisites."
    )
    
    # Schema
    schema_type: Literal["HowTo", "TechArticle", "Article"] = Field(
        default="HowTo",
        description="Primary schema.org type."
    )
    
    # Content Strategy
    target_audience: List[str]
    tone: Literal[
    "Professional", "Conversational", "Authoritative", "Friendly", 
    "Encouraging", "Neutral", "Persuasive", "Analytical", 
    "Direct", "Action-oriented", "Trustworthy", "Urgent"
    ]
    target_word_count: int = Field(ge=800, le=5000)
