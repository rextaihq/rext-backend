"""
Personas Module

This module manages persona configurations for content generation.
Personas define the voice, expertise, and style characteristics that
should be injected into content for E-E-A-T enhancement.
"""

from src.flow.model.personas.eeat_personas import get_eeat_persona

__all__ = ["get_eeat_persona"]
