"""
Humanization Human Message Template

This module provides the human message template for content humanization.
It formats content for the LLM to transform into naturally human-written text.
"""

from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.humanize import HUMANIZE_SYSTEM_PROMPT


def get_humanize_prompt() -> ChatPromptTemplate:
    """
    Returns a ChatPromptTemplate for content humanization.
    
    Template variables:
        - title: Content title to humanize
        - body_markdown: Content body in markdown format
    
    Returns:
        ChatPromptTemplate configured for humanization (90% human-written target)
    """
    return ChatPromptTemplate.from_messages([
        ("system", HUMANIZE_SYSTEM_PROMPT),
        ("human", """**Your Task**: Completely rewrite the following content to make it sound like it was written by a real person with personality, not AI. The content should feel natural, conversational, engaging, and authentic.

**Original Content:**
Title: {title}

{body_markdown}

**Output Instructions:**
- Rewrite to sound VERY naturally human with strong personality
- Target: 90% human-written detection score (10% AI)
- Keep all factual information intact
- Maintain markdown formatting
- Make it highly engaging, conversational, and authentic
- Break formal writing rules when it sounds more natural
- Add personality and unique voice throughout


**Prompt Example**
Prompt:
Blog keyword = How to get a high-quality backlink

No fluff, no cringe, every sentence on a new line, make my articles win-win, normal language with a reading grade of 4, keep it neutral.

Kick off with real questions and worries your audience faces. Use plain talk to hit the mark, skipping the tech talk unless it’s what everyone’s chatting about.

Sprinkle in stories and examples like you’re sharing insights over coffee with a friend. This touch of personal flair makes your tips stick.

Nothing generic. Keep every word very specific.

Weave in keywords like you’re searching for a dish - just enough to taste but not so much it spoils the meal. Pop them into titles, subtitles, and the body, making sure they fit snugly into the conversation.

Chop up complex tips into bullet points, lists and bold highlights. This makes it a breeze for both people and search engines to skim through.

Throw in visuals - photos, clips or infographics - to mix things up. Give each picture a catchy, keyword-rich description to catch both eyes and search engines.

Nudge the readers to chat, share and engage with your content. It’s a two-way street that amps up the value for both your audience and search engines.

Stay fresh and current by regularly refreshing your content. It keeps you in the search engine's good graces and strengthens bonds with your audience.

Ditch the jargon like “digital landscape” for something more down-to-earth and straightforward. Keep it real, keep it fresh, and keep it engaging. 
""")
    ])
