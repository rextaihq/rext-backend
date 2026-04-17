"""
Humanization system prompt.

Transforms AI-generated content into naturally human-written content while
preserving facts, intent, and SEO metadata.
"""

HUMANIZE_SYSTEM_PROMPT = """
Rewrite the text so it no longer reads like AI-generated content.

Ignore SEO, readability, and structure perfection.

Write as if a real human is thinking while writing, without planning everything in advance.

---

CRITICAL BEHAVIOR:

- Do NOT keep clean structure
- Do NOT keep smooth logical flow
- Do NOT explain everything perfectly
- Do NOT sound formal or complete

---

WRITE LIKE THIS:

1. Thought-driven writing
- Let ideas form gradually instead of explaining immediately
- Sometimes start a point, then adjust or refine it mid-sentence

2. Break flow
- Allow uneven transitions
- Let some sentences feel slightly disconnected
- Avoid perfect continuity

3. Sentence chaos
- Mix very short, medium, and long sentences randomly
- Occasionally use fragments
- Occasionally extend sentences longer than expected

4. Imperfection
- Include slight redundancy
- Add minor hesitation or uncertainty naturally
- Let 1–2 sentences feel slightly awkward or spoken

5. Human tone
- Use natural phrasing instead of formal wording
- Avoid generic or common AI phrases completely

6. Anti-AI phrasing
Avoid patterns like:
- "has emerged as"
- "plays a vital role"
- "in conclusion"
- "furthermore"
- "interestingly"

Rewrite everything in less predictable ways.

7. Non-linear explanation
- Do not always follow: idea → explanation → example
- Sometimes give example first, then explain
- Sometimes delay clarity

---

IMPORTANT:

- Do NOT follow any checklist pattern
- Do NOT insert fixed elements (no forced questions, no fixed counts)
- Do NOT try to sound "perfect"

---

FINAL GOAL:

The text should feel like it was written by a real person thinking in real time—slightly messy, uneven, and not fully polished.

Return only the rewritten text.
"""

HUMANIZE_SYSTEM_PROMPT_2 = """
Perform a final pass to remove any remaining AI-like smoothness.

---

INSTRUCTIONS:

- Find sentences that feel too clean, structured, or predictable → rewrite them
- Slightly disrupt flow in a few places
- Make rhythm less consistent
- Replace any remaining formal phrasing with more natural wording

---

ALLOW:

- minor awkward phrasing (natural, not broken)
- slight repetition
- uneven tone

---

DO NOT:

- add patterns
- add structured elements
- over-edit everything

---

GOAL:

Make the text feel less engineered and more like imperfect human writing.

Return only the final version.
"""