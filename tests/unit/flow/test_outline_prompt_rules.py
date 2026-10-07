"""The outline prompts ask for headings in the title's case and two points a section (G65)."""

from src.flow.prompts.human.outline import get_outline_prompt
from src.flow.prompts.system.outline import OUTLINE_GENERATION_PROMPT


def _text() -> str:
    template = get_outline_prompt()
    return "\n".join(str(message.prompt.template) for message in template.messages)


def test_headings_follow_the_titles_case():
    text = _text()
    assert "in the title's capitalization style" in text
    assert "Never mix the two in one outline" in text
    # The format's example no longer shows a Title Case heading for a sentence-case title to copy.
    assert "H2: Section Title" not in OUTLINE_GENERATION_PROMPT


def test_every_section_has_at_least_two_points():
    assert "never fewer than 2" in _text()
    assert OUTLINE_GENERATION_PROMPT.count("Key points to cover (at least two)") == 2
