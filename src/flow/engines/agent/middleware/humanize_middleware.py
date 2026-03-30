from typing import Optional, Any
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langgraph.runtime import Runtime

from src.flow.states.rext import REXT


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
You are an expert human content editor. Your only job is to rewrite the article text \
given to you so that it reads like it was written by an experienced, thoughtful human — \
not a language model.

========================
WHAT TO PRESERVE (never change these)
========================
- All markdown headings (##, ###, etc.) — keep them word-for-word
- All bold/italic formatting (**text**, *text*)
- All numbered and bulleted lists — keep every item, just rewrite the prose
- All inline code, code blocks, and technical terms
- All facts, statistics, percentages, and numbers
- All source citations and URLs that appear in the text
- All SEO keywords as they appear in headings and key sentences
- The overall structure and section order

========================
WHAT TO REWRITE
========================
- Sentence structure — vary length, mix short punchy sentences with longer detailed ones
- Transitions — replace generic connectors ("Additionally", "Furthermore", \
"It is important to note that") with natural language
- Paragraph openings — avoid starting multiple paragraphs with "This", "These", "When", "The"
- Redundant phrasing — cut filler like "In conclusion", "As mentioned earlier", \
"It should be noted"
- Passive voice — convert to active where it sounds more natural
- Robotic patterns — rewrite anything that sounds like a template or AI fill-in
- Readability — target Flesch Reading Ease of 60–70 (clear, direct prose)

========================
TONE
========================
- Confident and clear, like an expert explaining something to a peer
- Conversational where it fits, but never informal or sloppy
- Never hype or exaggeration — grounded and trustworthy

========================
OUTPUT RULES
========================
- Return ONLY the rewritten markdown text
- Do NOT add any explanation, preamble, or comments
- Do NOT add new sections, headings, or content that was not in the original
- Do NOT remove any section that existed in the original
- The rewritten text must be at least 90%% of the original length
"""

    def __init__(self, model: BaseChatModel):
        """
        Args:
            model: The same chat model used by the content agent.
                   Passed from create_content_agent so we reuse the
                   already-initialised instance rather than loading a new one.
        """
        self.model = model

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

        # --- Humanize body_markdown ----------------------------------------
        humanized_body = body_markdown
        if body_markdown:
            print("  [HumanizeMiddleware] ↻ Humanizing body_markdown ...")
            humanized_body = await self._humanize(body_markdown)
            print(f"  ✓ body done       : {len(humanized_body):,} chars")

        # --- Humanize introduction -----------------------------------------
        humanized_intro = introduction
        if introduction:
            print("  [HumanizeMiddleware] ↻ Humanizing introduction ...")
            humanized_intro = await self._humanize(introduction)
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

        # Mutate state in-place — same pattern as PersonaInjectionMiddleware
        state["messages"][last_ai_idx] = new_ai_msg

        print("[HumanizeMiddleware] ✓ State updated with humanized content\n")

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

    async def _humanize(self, text: str) -> str:
        """
        Send text to the model with the humanize system prompt.
        Falls back to the original text when the model returns empty or
        suspiciously short output (< 50 % of original length).
        """
        try:
            response = await self.model.ainvoke(
                [
                    SystemMessage(content=self.HUMANIZE_SYSTEM_PROMPT),
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
            print(f"  [HumanizeMiddleware] ✗ Humanization error: {exc}")
            return text
