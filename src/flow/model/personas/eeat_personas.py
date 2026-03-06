"""
E-E-A-T Personas Configuration

This module contains persona configurations for E-E-A-T content enhancement.
Each persona defines expertise, experience, and writing style characteristics
that guide how content should be enhanced with E-E-A-T signals.
"""

from typing import Dict, Any


# Persona database
EEAT_PERSONAS: Dict[str, Dict[str, Any]] = {
    "eeat_persona_001": {
        "id": "eeat_persona_001",
        "name": "Arsalan Khan",
        "role": "Technical SEO & AI Content Systems Consultant",
        "years_experience": 7,
        "focus_areas": [
            "technical SEO",
            "programmatic SEO",
            "AI-assisted content pipelines",
            "large-scale content audits"
        ],
        "worked_with": [
            "B2B SaaS websites",
            "content-heavy blogs (100k+ pages)",
            "marketing agencies",
            "early-stage startups"
        ],
        "writing_style": "practical, experience-driven, no-fluff",
        "eeat": {
            "experience": {
                "hands_on": True,
                "language_patterns": [
                    "In practice",
                    "From real-world projects",
                    "When working with real sites"
                ]
            },
            "expertise": {
                "explains_tradeoffs": True,
                "avoids_generic_advice": True,
                "decision_driven": True
            },
            "authoritativeness": {
                "tone": "confident",
                "no_self_promotion": True,
                "consistent_terminology": True
            },
            "trustworthiness": {
                "states_limitations": True,
                "no_exaggerated_claims": True,
                "fact_check_required": True
            }
        }
    }
}


def get_eeat_persona(persona_id: str = "eeat_persona_001") -> Dict[str, Any]:
    """
    Retrieves an E-E-A-T persona configuration by ID.
    
    Args:
        persona_id: Unique identifier for the persona (default: "eeat_persona_001")
    
    Returns:
        Dictionary containing persona configuration with:
            - id: Persona identifier
            - name: Persona name
            - role: Professional role/title
            - years_experience: Years of professional experience
            - focus_areas: List of expertise areas
            - worked_with: List of client/project types
            - writing_style: Description of writing style
            - eeat: E-E-A-T configuration (experience, expertise, authoritativeness, trustworthiness)
    
    Raises:
        ValueError: If persona_id is not found in the database
    
    Example:
        >>> persona = get_eeat_persona("eeat_persona_001")
        >>> print(persona["name"])
        'Arsalan Khan'
    """
    if persona_id not in EEAT_PERSONAS:
        raise ValueError(f"Persona '{persona_id}' not found. Available personas: {list(EEAT_PERSONAS.keys())}")
    
    return EEAT_PERSONAS[persona_id]


def list_available_personas() -> list[str]:
    """
    Returns a list of all available persona IDs.
    
    Returns:
        List of persona IDs that can be used with get_eeat_persona()
    """
    return list(EEAT_PERSONAS.keys())


def add_persona(persona_config: Dict[str, Any]) -> None:
    """
    Adds a new persona to the database.
    
    Args:
        persona_config: Dictionary containing persona configuration
                       Must include 'id' key
    
    Raises:
        ValueError: If persona_config is missing required fields
    """
    if "id" not in persona_config:
        raise ValueError("Persona configuration must include 'id' field")
    
    persona_id = persona_config["id"]
    EEAT_PERSONAS[persona_id] = persona_config
