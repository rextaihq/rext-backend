from typing import Optional, Any
from uuid import UUID
from sqlalchemy import select
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langgraph.runtime import Runtime

from src.flow.states.rext import REXT
from src.flow.model.structure.content import GeneratedContent


class HumanizeMiddleware(AgentMiddleware[REXT]):
    """
    Runs after the agent loop completes (aafter_agent hook).

    1. Finds the last AIMessage that holds the GeneratedContent tool call
    2. Extracts body_markdown and introduction from the tool call args
    3. Calls the same model the agent uses to rewrite both fields — naturally human-written
    4. Preserves all markdown structure, headings, facts, links, and SEO signals
    5. Replaces the tool call args in-place so downstream graph nodes get humanized content

    Usage in content_agent.py:
        HumanizeMiddleware(model=model)
    """

    state_schema = REXT

    HUMANIZE_SYSTEM_PROMPT = """\
You are a human writer with a distinct personal voice. Rewrite or write 
the following content as if it came from a real person with lived 
experience — not an AI assistant.

Follow these rules strictly:

INPUT: 
- Audience: {target_audience}
- Context: {persona_description} + [where it's posted + why they're reading]
- Outcome: {persona_goals}  
- Content Type: {content_type}

TOPIC:
- Topic: {selected_topic}
- Must Cover: [bullets]
- Must NOT Cover: [optional]
- Length: {word_count} 
- Content Tone: {content_tone}
- POV: 1st person
- Region/Examples: [optional]

E-E-A-T INJECTION (Writer Personality):
- Writer Name: {persona_full_name}
- Role/Title: {persona_professional_title}
- Years Doing This: [#]
- Proof Points (pick 3–6): [ships/features, clients, scale handled, audits, migrations, incidents fixed, contributions, certifications]
- Typical Stack/Tools: {persona_areas_of_expertise}
- What You're Biased Toward (your stance): [e.g., "boring + reliable"]
- What You Avoid (and why): [e.g., "too many plugins", "premature microservices"]
- Boundaries/Limits: [what you don't know / assumptions you're making]
- Bio / Credibility Line: {persona_bio} + If relevant, include 1–2 credibility lines early (NOT a full bio wall).
- Behaviors / Style Guidance: {persona_behaviors}
- Personal Tone: {persona_tone_of_voice}

VOICE & STYLE:
- Use a slightly informal, conversational tone even in professional content
- Vary sentence length dramatically — mix very short sentences with longer 
  ones. Like this. Then follow it with something more elaborate and nuanced.
- Occasionally start sentences with "And", "But", or "So" — real writers do this
- Use contractions naturally (don't, it's, you'll, they're)
- Throw in a mild imperfection or two — a rhetorical question, a brief 
  tangent, or a self-correction ("well, sort of...")

WORD CHOICE:
- Avoid these overused AI phrases: "Furthermore", "In conclusion", 
  "It's worth noting", "Delve into", "Comprehensive", "Utilize", 
  "In today's world", "Leverage", "It is important to note"
- Use specific, concrete words over abstract ones
- Occasionally use informal fillers like "honestly", "look", "here's 
  the thing", "to be fair"
- Include at least one niche or domain-specific term used casually, 
  as if you already know your audience

STRUCTURE:
- Don't make every paragraph the same length
- Avoid perfectly symmetrical lists — if you use bullet points, make 
  them uneven in length
- Break a grammar rule intentionally, once. Fragments are fine.
- Don't wrap up too neatly — avoid a clean "conclusion" paragraph that 
  summarizes everything

PERSPECTIVE:
- Write with a point of view — have a mild opinion or preference
- Reference a realistic scenario, example, or hypothetical that feels 
  grounded ("imagine you're reviewing a PR at 11pm...")
- Show slight uncertainty where appropriate ("probably", "in most cases", 
  "I'd argue")

You are [NAME], a [PROFESSION] with [X] years of hands-on experience 
in [NICHE/INDUSTRY]. You've worked with [type of clients/companies], 
seen real failures and wins, and you write from that place — not from 
textbooks.

PERSONA IDENTITY (E-E-A-T CORE):
- Experience: You've personally done this. Reference it naturally. 
  Not "studies show" — but "when I ran a campaign for a mid-size 
  e-commerce brand last year..."
- Expertise: You know the insider terms, the shortcuts, the things 
  that actually matter vs. what sounds good in theory
- Authoritativeness: You've seen others get this wrong. You have a 
  mild but clear opinion about the right way
- Trustworthiness: You acknowledge limitations. You say "this won't 
  work for everyone" or "honestly, it depends on your situation"

VOICE & STYLE:
- Slightly informal, conversational — even in professional content
- Vary sentence length dramatically. Short punchy ones. Then something 
  longer that explains the nuance behind what you just said, because 
  context matters and people deserve more than a hot take.
- Occasionally start sentences with "And", "But", or "So"
- Use contractions naturally (don't, it's, you'll, they're)
- Throw in a mild imperfection — a rhetorical question, brief tangent, 
  or self-correction ("well, sort of...")
- Write like you're talking to a colleague, not presenting to a board

WORD CHOICE:
- Ban list — never use these: "Furthermore", "In conclusion", 
  "It's worth noting", "Delve into", "Comprehensive", "Utilize", 
  "In today's world", "Leverage", "It is important to note", 
  "Multifaceted", "Pivotal", "Robust", "Underscore", "Embark", 
  "Streamline", "Game-changer", "Unlock"
- Use specific, concrete words over vague abstract ones
- Use informal fillers naturally: "honestly", "look", "here's the 
  thing", "to be fair", "and yeah"
- Drop in at least one industry-specific term casually — like your 
  reader already knows it

E-E-A-T INJECTIONS (use at least 3 of these):
- "In my experience working with [type of client/project]..."
- "I've seen this go wrong when..."
- "Most people skip this step, but it's actually the one that..."
- "Honestly, when I first tried this I thought [X], but..."
- "The standard advice is [X] — and look, it's not wrong, but..."
- "A client once asked me [question] and my answer surprised them..."
- "I'd probably approach it differently now than I did 3 years ago..."
- "This is the part nobody talks about..."

STRUCTURE:
- Paragraphs should be uneven in length — that's natural
- If using bullet points, make them uneven in length too
- Break one grammar rule on purpose. Fragments work.
- No clean summarizing conclusion — end on a thought, an opinion, 
  or a next step, not a bow-tied wrap-up

PERSPECTIVE:
- Have a real point of view — mild but clear
- Reference a grounded scenario or hypothetical 
  ("imagine you're 2 days before a product launch and...")
- Show appropriate uncertainty ("probably", "in most cases", 
  "I'd argue", "could be wrong but...")
- Don't hedge everything — some things you know from experience 
  and you can say so directly

AFTER WRITING, do this revision pass:
1. Replace any word used more than twice with a synonym
2. Find the single most AI-sounding sentence — rewrite it 
   bluntly in plain English
3. Add one hyper-specific detail that proves you've done this 
   (a number, a tool name, a real scenario)
4. Cut every sentence that doesn't add meaning — tighten hard
5. Check the opening line — if it could appear in any generic 
   article, rewrite it as something only this persona would say

Now write/rewrite the following content.
"""

    def __init__(
        self,
        model: BaseChatModel,
        workspace_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        persona_id: Optional[UUID] = None,
        outline: Optional[dict] = None,
    ):
        """
        Args:
            model: The same chat model used by the content agent.
            workspace_id: For DB fetches.
            user_id: Caller's ID.
            persona_id: Persona DB ID.
            outline: Optional outline dict.
        """
        self.model = model
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.persona_id = persona_id
        self.outline = outline

    # ------------------------------------------------------------------ #
    # Main hook: runs AFTER agent loop completes                           #
    # ------------------------------------------------------------------ #

    async def aafter_agent(self, state: REXT, runtime: Runtime) -> None:
        print("\n[HumanizeMiddleware] ▶ aafter_agent triggered")

        messages = state.get("messages") or []
        if not messages:
            print("  [HumanizeMiddleware] ✗ No messages in state, skipping")
            return

        # Find the last AIMessage that contains a GeneratedContent tool call
        last_ai_idx, last_ai_msg = self._find_last_tool_call_message(messages)

        if last_ai_msg is None:
            print("  [HumanizeMiddleware] ✗ No AIMessage with tool_calls found, skipping")
            return

        tool_call = last_ai_msg.tool_calls[0]
        args: dict = dict(tool_call.get("args") or {})

        body_markdown: str = args.get("body_markdown") or ""
        introduction: str = args.get("introduction") or ""

        if not body_markdown and not introduction:
            print("  [HumanizeMiddleware] ✗ body_markdown and introduction both empty, skipping")
            return

        print(f"  body_markdown   : {len(body_markdown):,} chars")
        print(f"  introduction    : {len(introduction):,} chars")

        # Fetch Persona & format System Prompt
        persona = None
        if self.workspace_id:
            from src.api.database.async_database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                persona = await self._fetch_persona(db)

        outline = self.outline or (state.get("content") or {}).get("outline") or {}

        # Safe defaults
        target_audience = ", ".join(outline.get("target_audience", [])) if isinstance(outline.get("target_audience"), list) else str(outline.get("target_audience", "General audience"))
        content_type = outline.get("schema_type", "Article")
        selected_topic = outline.get("title", "The topic")
        word_count = str(outline.get("target_word_count", "Appropriate length"))
        content_tone = outline.get("tone", "Conversational")

        persona_full_name = "an expert"
        persona_description = "A knowledgeable professional"
        persona_goals = "Provide value and clarity"
        persona_professional_title = "Industry Expert"
        persona_areas_of_expertise = "best practices and deep insights"
        persona_bio = "You have years of real-world experience."
        persona_behaviors = "Writes clearly and practically."
        persona_tone_of_voice = content_tone

        if persona:
            persona_full_name = persona.full_name or persona.name or persona_full_name
            persona_description = persona.demographics or persona_description
            persona_goals = persona.goals or persona_goals
            persona_professional_title = persona.professional_title or persona_professional_title
            persona_areas_of_expertise = persona.areas_of_expertise or persona_areas_of_expertise
            persona_bio = persona.bio or persona_bio
            persona_behaviors = getattr(persona, "behaviors", persona.demographics or "Writes naturally")
            persona_tone_of_voice = persona.tone_of_voice or persona_tone_of_voice

        system_prompt_content = self.HUMANIZE_SYSTEM_PROMPT.format(
            target_audience=target_audience,
            persona_description=persona_description,
            persona_goals=persona_goals,
            content_type=content_type,
            selected_topic=selected_topic,
            word_count=word_count,
            content_tone=content_tone,
            persona_full_name=persona_full_name,
            persona_professional_title=persona_professional_title,
            persona_areas_of_expertise=persona_areas_of_expertise,
            persona_bio=persona_bio,
            persona_behaviors=persona_behaviors,
            persona_tone_of_voice=persona_tone_of_voice,
        )

        # --- Humanize body_markdown ----------------------------------------
        humanized_body = body_markdown
        if body_markdown:
            print("  [HumanizeMiddleware] ↻ Humanizing body_markdown ...")
            humanized_body = await self._humanize(body_markdown, system_prompt_content)
            print(f"  ✓ body done       : {len(humanized_body):,} chars")

        # --- Humanize introduction -----------------------------------------
        humanized_intro = introduction
        if introduction:
            print("  [HumanizeMiddleware] ↻ Humanizing introduction ...")
            humanized_intro = await self._humanize(introduction, system_prompt_content)
            print(f"  ✓ intro done      : {len(humanized_intro):,} chars")

        # --- Rebuild AIMessage with updated args ---------------------------
        updated_args = {
            **args,
            "body_markdown": humanized_body,
            "introduction": humanized_intro,
        }
        updated_tool_call = {**tool_call, "args": updated_args}
        new_tool_calls = [updated_tool_call] + list(last_ai_msg.tool_calls[1:])

        new_ai_msg = AIMessage(
            content=last_ai_msg.content,
            tool_calls=new_tool_calls,
            id=last_ai_msg.id,
            name=last_ai_msg.name,
            additional_kwargs=dict(last_ai_msg.additional_kwargs),
        )

        # Mutate state by returning the updates for LangGraph / AgentMiddleware
        # and update the structured_response so the final_output has the humanized data
        generated_content = GeneratedContent(**updated_args)
        
        print("[HumanizeMiddleware] ✓ State updated with humanized content\n")
        return {
            "messages": [new_ai_msg],
            "structured_response": generated_content
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _find_last_tool_call_message(
        self, messages: list
    ) -> tuple[int, Optional[AIMessage]]:
        """
        Scan messages in reverse to find the last AIMessage that has tool_calls.
        Returns (index, message) or (-1, None) when not found.
        """
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                return i, msg
        return -1, None

    async def _humanize(self, text: str, system_prompt_content: str) -> str:
        """
        Send text to the model with the humanize system prompt.
        Falls back to the original text when the model returns empty or
        suspiciously short output (< 50 % of original length).
        """
        try:
            response = await self.model.ainvoke(
                [
                    SystemMessage(content=system_prompt_content),
                    HumanMessage(
                        content=(
                            "Rewrite the following article text to sound naturally "
                            "human-written. Follow the rules exactly.\n\n"
                            "---\n\n"
                            + text
                        )
                    ),
                ]
            )
            result: str = (
                response.content if hasattr(response, "content") else str(response)
            )
            # Safety guard: if output is suspiciously short keep the original
            if result and len(result) >= len(text) * 0.5:
                return result
            print(
                f"  [HumanizeMiddleware] ⚠ Model returned short output "
                f"({len(result)} chars vs {len(text)} original), keeping original"
            )
            return text
        except Exception as exc:
            return text

    async def _fetch_persona(self, db) -> Optional[Any]:
        from src.api.models.knowledge_models.persona_model import Persona
        
        if not self.workspace_id:
            return None
            
        if self.persona_id is not None:
            result = await db.execute(
                select(Persona).where(
                    Persona.id == self.persona_id,
                    Persona.workspace_id == self.workspace_id,
                )
            )
        else:
            result = await db.execute(
                select(Persona)
                .where(Persona.workspace_id == self.workspace_id)
                .order_by(Persona.created_at.desc())
                .limit(1)
            )
        return result.scalar_one_or_none()

