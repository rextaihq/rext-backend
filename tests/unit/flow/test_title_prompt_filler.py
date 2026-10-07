"""The title prompts say what filler is, and what to add in its place (G65, #560).

Staging, 2026-10-07: a candidate read "How to start a podcast on YouTube: Essential Tips Here".
Both prompts already told the model not to pad a title; neither said what padding looks like.
"""

from unittest.mock import AsyncMock

import pytest

from src.flow.engines.content.generation import topic_generation as tg
from src.flow.model.structure.topics import SEOTopic, SEOTopics

KEYPHRASE = "how to start a podcast"


def test_the_title_prompt_names_filler_and_what_to_add_instead():
    prompt = tg._build_system_prompt(
        keyphrase=KEYPHRASE,
        current_year=2026,
        selected_intent="informational",
        selected_content_type="how-to guide",
    )

    assert '"Essential Tips Here"' in prompt
    assert "would fit any title" in prompt
    assert "who it is for, a number of steps or items, the outcome, or the year" in prompt


@pytest.mark.asyncio
async def test_the_repair_prompt_names_filler_too():
    too_short = SEOTopics(topics=[SEOTopic(title="How to Start a Podcast", recommended=True)])
    model = AsyncMock()
    model.ainvoke.return_value = too_short

    await tg._repair_invalid_titles(
        model=model, parsed=too_short, query=KEYPHRASE, keyphrase=KEYPHRASE
    )

    sent = "\n".join(str(message.content) for message in model.ainvoke.call_args.args[0])
    assert '"Essential Tips Here"' in sent
    assert "Add who it is for, a number, the outcome or the year instead" in sent
