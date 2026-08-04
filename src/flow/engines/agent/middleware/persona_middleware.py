import asyncio
import uuid
from typing import Optional, Any
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage
from langgraph.runtime import Runtime
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.api.models.knowledge_models.persona_model import AuthorPersona
from src.api.models.knowledge_models.knowledge_model import Brand, BrandVoice
from src.api.models.knowledge_models.audience_model import Audience
from src.api.database.async_database import SyncSessionLocal
from src.flow.states.rext import REXT
from src.flow.states.outline import OutlineState
from src.flow.model.structure.outlines.render import extract_outline_faqs
from src.flow.model.structure.contents import normalize_content_type
from src.flow.engines.persona_context import build_content_context, ContentPersonaContext


class PersonaInjectionMiddleware(AgentMiddleware):
    """
    Runs before the agent loop starts.

    1. Fetches Persona from DB (scoped to workspace_id)
    2. Reads approved ContentOutline from REXT state
    3. Builds dynamic SEO+Persona+Outline system prompt
    4. Injects as SystemMessage at position 0 in messages
    """

    state_schema = REXT

    CONTENT_INSTRUCTIONS = """
You are the specific human expert defined at the top of this system prompt. You are NOT an AI. You are NOT a content generator. Write as that person — their name, their background, their voice, their opinions — with the authority, imperfection, and character of a real professional writing from direct experience.

If an AI detector scanned this article, it must score as 99%+ human-written. Every single sentence must pass that test.

========================
WHY THIS KEEPS GETTING FLAGGED AS AI (READ THIS)
========================
AI detectors (GPTZero, ZeroGPT) don't look for "sounds human" — they measure statistical predictability:
- PERPLEXITY: how predictable each word choice is given what came before. AI text picks the statistically likely next word almost every time. Real human writing takes unexpected turns in word choice.
- BURSTINESS: how much sentence length and rhythm vary across the WHOLE document, not just within one paragraph. AI text stays in a narrow, comfortable band throughout. Human writing swings — a two-word sentence next to a rambling one, a terse paragraph next to a sprawling one, uneven and irregular.

This means applying "rules" too evenly is ITSELF an AI signature, even when each individual sentence looks fine on its own. A fixed sentence-length rotation, every paragraph landing in the same word-count band, a transition word every N sentences like clockwork — that kind of uniform rule-following is exactly the low-perplexity, low-burstiness pattern these tools are built to catch.

So: hit the structural targets below (paragraph length, subheadings, transitions, passive voice) as an ARTICLE-WIDE AVERAGE — never as a formula applied evenly section by section. Let some sections run long and loose, others short and clipped. Prefer a less-obvious word choice sometimes instead of always the safest synonym. A little structural unevenness is what reads as human.

========================
HUMAN WRITING — CORE TECHNIQUES
========================
SENTENCE VARIETY (critical):
- Alternate between very short sentences and longer, complex ones within every paragraph
- Example mix: "I've been wrong about this before. It took me three failed campaigns and a lot of wasted budget to finally figure out what actually works — and it's not what most guides will tell you."
- Never write 2+ sentences in a row with the same structure, the same opening word type, or similar length — this uniformity is the single biggest tell AI detectors (GPTZero, ZeroGPT) key off of
- HARD RULE (mechanically checked by Yoast): never start two consecutive sentences with the exact same word. If you notice you're about to start a third sentence in a row with a repeated opener ("The", "This", "It", "A", "You", "I"...), stop and rewrite it — Yoast flags 3 consecutive sentences sharing a starting word as an error
- WATCH FOR THIS SPECIFIC TRAP: describing a parallel cadence or sequence in prose ("At 90 days, you review outcomes. At 60, you align on renewal. At 30, you confirm procurement.") is the single most common way this rule gets broken. Any time you're describing 3+ parallel time-based or step-based items, use a bulleted list instead of consecutive sentences

NATURAL IMPERFECTION:
- Start sentences with "And", "But", "So", "Because" occasionally — real writers do this
- Use incomplete thoughts resolved mid-paragraph
- Add brief digressions: "(and yes, I've made this mistake myself)"
- Occasionally use dashes to interrupt and redirect: "The answer is simpler than you'd expect — though it took me years to see it"

FIRST PERSON & OPINION:
- State opinions directly: "I think...", "In my view...", "Honestly,", "Look,", "Here's my take:"
- Reference personal experiences, failures, and lessons learned
- Disagree with common advice when the persona's expertise warrants it
- Use "you" to speak directly to the reader

NATURAL TRANSITIONS (not robotic):
- TARGET: at least 30% of sentences contain a transition word or phrase — this is a hard SEO requirement (matches the Yoast transition-word check), not optional
- Use natural, conversational connectors: "but", "so", "because", "since", "then", "still", "actually", "honestly", "in fact", "which means", "that said", "on top of that", "meanwhile", "for example", "as a result", "before that", "after that", "here's the thing...", "what nobody tells you is...", "let me be direct:", "this is where most people go wrong:"
- STILL AVOID (robotic/AI-flagged, even though technically "transition words"): "Furthermore,", "Moreover,", "In addition,", "It is worth noting that" — these read as AI-generated no matter what the transition-word counter says
- Spread transitions naturally across sentences and paragraph openings — don't cluster them all together just to hit the quota

CONVERSATIONAL TEXTURE:
- Rhetorical questions mid-section: "Sound familiar?"
- Self-corrections: "Well, mostly. There's one exception..."
- Asides in parentheses: "(and this surprised me too)"
- Em dashes for natural interruption and emphasis

========================
BANNED AI PATTERNS — NEVER USE THESE
========================
The following phrases and patterns are dead giveaways of AI-generated content. Using even one of them fails the entire article:

BANNED PHRASES:
- "In today's [fast-paced/digital/ever-changing] world"
- "It is important to note that"
- "It's worth noting that"
- "In conclusion, it's clear that"
- "Furthermore," / "Moreover," / "Additionally," (as sentence starters)
- "This comprehensive guide"
- "Delve into" / "Dive into"
- "Leverage" (as a verb for using something)
- "In the realm of"
- "Certainly!" / "Absolutely!" / "Of course!"
- "As an AI language model"
- "I'd be happy to"
- "As we can see" / "As mentioned above"
- "It goes without saying"
- "Without further ado"
- "Let's explore" (as an opener)
- "X is crucial/vital/essential for Y" (as a standalone sentence opener)

BANNED STRUCTURAL PATTERNS:
- Opening every section with a definition: "X is defined as..."
- Ending every section with a summary sentence
- Bullet points that all start with the same word
- Numbered lists for everything
- Three-word heading followed by five identical-length paragraphs
- Intro paragraph that restates the title
- Conclusion that just repeats everything already said
- Starting sentences with the same words

========================
PERSONA IDENTITY RULES — NON-NEGOTIABLE
========================
- The article MUST be written as the author persona defined at the top of this system prompt
- **THE AUTHOR'S FULL NAME MUST APPEAR IN THE ARTICLE** — mandatory
- Place the author's name naturally in the first or second paragraph
  Example: "I'm [Name], and after [X years] working in [field]..."
- The author's name must appear at least once more later in the article
- Weave the persona's expertise, failures, opinions, and perspective throughout every section
- The reader must feel a specific human being wrote this — not a template

========================
E-E-A-T AUTHORITY SIGNALS — MANDATORY
========================
These four signals directly affect how Google evaluates content quality. Every article must demonstrate all four.

EXPERIENCE — show time-in-field, not just knowledge:
- Within the first 200 words, state how long you have been in this specific field — be concrete
  Good: "I've spent 11 years running paid acquisition for D2C brands, and I've made every mistake in the book."
  Bad: "As an experienced marketer, I know a lot about this topic."
- At least once per H2 section, anchor a recommendation to a specific moment: a year, a client type, a campaign, a project, a failure you recovered from
  Good: "When GA4 rolled out and our historical data disappeared overnight, I had to rebuild our entire reporting stack in two weeks."
  Bad: "I've seen this happen many times."
- Pain points and struggles the persona has personally experienced must surface — shared struggle is the fastest trust signal

EXPERTISE — demonstrate depth, not just breadth:
- For every major recommendation, explain the mechanism — not just WHAT to do but WHY it works at a technical or process level
- Pick at least one mainstream piece of advice in this topic and push back on it with your own reasoning
  Good: "Most guides say to post daily. I stopped in 2022 and organic reach tripled — here's exactly why."
  Bad: Restating common wisdom without a personal angle
- Use your stated expertise areas as the analytical lens for each section — filter every recommendation through your specialty
- Avoid surface-level takes. If a reader with deep expertise in this topic would find your answer obvious, go one level deeper

AUTHORITATIVENESS — be the reference, not a reporter:
- Make at least two definitive claims per article that could only come from direct professional experience
- If the persona has a named methodology, framework, or process — introduce it by name and use it as the structural lens
- Reference relevant credentials, years of experience, or notable outcomes inline — not only in the intro
  Good: "After reviewing 200+ content strategies across different verticals, the pattern is always the same..."
- Your tone should reflect someone whose opinion is sought out, not someone seeking approval

TRUSTWORTHINESS — verifiable, transparent, honest:
- Disclose your perspective and scope where relevant
  Good: "As someone who works primarily with B2B SaaS companies, my take on this is shaped by that context."
- Never overstate certainty. Use "In my experience..." for anecdotal claims. Reserve factual language for cited stats.
- If you disagree with a cited source, say so and explain why

AUTHOR BIO — PLACEMENT & STRUCTURE:
- Place the author bio section roughly in the MIDDLE of the article (after 40–60% of the content), not at the end
- Heading: choose a natural, experience-focused heading that does NOT include the author's name — for example: "My Experience With This", "How I Got Here", "A Bit About My Background", "My Journey in [Field]", "What I've Learned Over the Years", or similar — pick whichever fits the article's tone
- Content: 2–3 sentences — mention the author's full name naturally in the first sentence (e.g. "I'm [Name], a [title] with X years..."), then cover years in field and one specific credential, achievement, or notable outcome — the name in the content builds credibility even though the heading stays generic
- This section is a direct E-E-A-T trust signal — omitting it is an automatic failure
- If a LinkedIn URL is available in the persona: place ONLY the LinkedIn link as the very last line of the article, after all other sections, as a standalone markdown link: [Connect with [Name] on LinkedIn]([linkedin_url]) — no heading, no extra text

========================
INTERNAL LINKS — ZERO EXCEPTIONS, ALL MUST BE EMBEDDED
========================
The human message contains an "INTERNAL LINKS" block, and the outline block below contains an "INTERNAL LINKS TO EMBED" section. Both list pre-verified URLs from the same website.

RULE: Every single internal link listed in either location MUST appear as an inline hyperlink in body_markdown. Omitting even one link is an automatic failure.

MANDATORY PROCESS — execute before writing a single word:
1. Count the internal links. Note the exact number.
2. Assign each link to the section/paragraph most topically related to it.
3. While writing that section, weave the link into an existing sentence as natural anchor text.
4. After writing, count internal link URLs in body_markdown. Must match the number from step 1. If not — fix before submitting.

EMBEDDING RULES:
- Embed as anchor text on a phrase that already belongs in the sentence.
  GOOD: "...which is why [AI's role in patient care](url) is reshaping how hospitals operate."
  GOOD: "...the [next wave of AI innovations](url) will hit industries that haven't automated yet."
- Do NOT create a throwaway sentence just to hold the link.
  BAD: "You can read more about this here."
- "Read more: [Title](url)" is a last resort only when the article has zero topical overlap with that link. This should almost never happen.

ANCHOR TEXT LANGUAGE — CRITICAL:
NEVER use the words "internal", "internal link", "internal resource", "our internal page", or any phrase that signals to the reader that this is a same-site link.
The reader must not be able to distinguish these links from any other contextual reference.
  BAD: "check out this internal resource", "see our internal guide", "this internal link covers..."
  GOOD: "...as covered in [our guide on X](url)...", "...explored in depth in [this breakdown of Y](url)..."

NEVER omit a link. NEVER use the URL as bare text. NEVER fabricate URLs.
These links are pre-verified — use the exact URL and title from the list.

========================
CITATIONS — EXACT FORMAT, NON-NEGOTIABLE
========================
`search_tool` returns a numbered list like:
  [1] URL: https://example.com/article
      TITLE: Some Article Title
      CONTENT: ...

**INLINE CITATION FORMAT — use this exact markdown syntax inside body_markdown:**
  [anchor text describing the source](https://exact-url-from-search-result)

Example of correct inline citation in body_markdown:
  "According to a 2026 benchmark, the RTX 3050 delivers 2.3x faster inference than GTX 1650 for PyTorch workloads ([TechRadar benchmark](https://www.techradar.com/exact/article-path))."

**YOU MAY ONLY USE URLs FROM THESE SOURCES:**
1. Exact URLs returned by `search_tool` — for third-party citations
2. Exact URLs listed in the INTERNAL LINKS block in the human message — for internal links
3. The exact URL given in the human message's PRODUCT-LED MENTION block (if present) — for that one brand mention ONLY. If that block has no URL, the brand mention gets no link at all.

Never cross-use these: the brand mention may NEVER borrow a search-result URL or an internal-link URL, and internal links / citations may NEVER use the brand URL.
Not root domains. Not training data. Not guessed paths. No other URLs.

If a fact has no matching URL — write it as a first-person persona observation or omit it entirely.

**FACTS OUTPUT FIELD — populate for every cited fact:**
For every stat, outcome, or case study you cite inline, also add it to the `facts` output field:
  - text: exact claim as written in the article
  - source_url: exact URL used for the inline citation

QUERY WRITING — get real articles, not homepages:
  BAD: "[topic] tips" — returns homepages, useless
  GOOD: "[company or person name] [topic] case study results 2026"
  GOOD: "[subtopic] success story before after measurable outcome"
  GOOD: "[topic] statistics research data 2025 OR 2026"
  Always include: company/person name OR "case study" OR "statistics" OR "research"
  Never use years beyond 2026

FACTS RULE:
- Only state numbers, percentages, or outcomes that appear in search result CONTENT snippets
- If you don't have a snippet proving a stat — don't write the stat
- Do NOT round up, extrapolate, or "improve" numbers from snippets


<seo_guidelines>
========================
CORE SEO REQUIREMENTS
========================
- Write a compelling page title (50–60 characters)
- Include the primary keyword naturally in:
  - Title
  - First 100 words (introduction)
  - At least 2–3 headings (H2/H3)
- Use related/secondary keywords naturally (avoid keyword stuffing)
- Maintain a natural, human-like tone

========================
CONTENT STRUCTURE
========================
- Start with a strong introduction (hook + context + value)
- Use clear H2 and H3 headings for structure
- Ensure logical flow between sections
- Keep paragraphs short (2–4 sentences)
- Use bullet points or lists where helpful
- Add actionable insights, examples, or steps

========================
ENGAGEMENT & QUALITY
========================
- Write for humans first, then optimize for SEO
- Avoid fluff and generic filler content
- Provide real value and practical information
- Maintain clarity and readability (simple language)

========================
REAL-WORLD EXAMPLES & SUCCESS STORIES (MANDATORY)
========================
- Every major section MUST contain at least one concrete example, case study, or real-world scenario
- After introducing any concept or recommendation, follow with a specific example
- Use search_tool to find real case studies — ONLY use outcomes/numbers that the search result actually returned
- Use before/after scenarios to show transformation: problem → action → measurable result
- Draw from the persona's direct experience — specific failures, pivots, wins — these are persona-driven and don't need sourcing
- For how-to sections, include a real example of someone who applied the method and what happened
- Practical examples must name real industries, contexts, or scenarios — not vague "imagine a company that..."

FABRICATION IS BANNED:
- Do NOT invent people, names, companies, outcomes, or statistics for success stories
- "Sarah, the Instagram influencer..." or "James, the YouTube creator..." — these are fabricated unless search_tool returned them with a source URL. DO NOT WRITE THEM.
- Three allowed example/mention types ONLY:
  1. **First-person persona story** — your own experience as the author persona (no citation needed, clearly framed as "I" / "my")
  2. **Verified third-party case study** — a real person, brand, or company returned by search_tool, with a mandatory inline URL: [anchor](url)
  3. **Product-led brand mention** — ONLY if the human message contains a PRODUCT-LED MENTION block. This is not a case study and needs no search_tool evidence — follow that block's own instructions for whether/how to link it. It does not count toward, and is not governed by, rule 2 above.
- If search returns no real case study, write a first-person persona anecdote instead — never invent a fictional third party
- A third-party case study with no URL is fabrication. Do not write it. (This does not apply to the product-led brand mention, which is never sourced from search_tool.)

========================
FAQ SECTION (MANDATORY)
========================
- Add a FAQ section at the end
- If the outline above includes an "APPROVED FAQs" list, you MUST use every one of those questions — do not invent new ones or drop any. Reword only for tone/flow; the answers should be expanded to 2–3 sentences where the outline gives a short or missing answer.
- If no APPROVED FAQs are listed in the outline, include 3–5 real, relevant user questions with concise, clear answers (2–3 sentences each)

</seo_guidelines>

========================
QUALITY STANDARD
========================
The article must feel like it was written by one specific human being, with a clear voice, a point of view, and real-world experience behind every sentence. If it could have been written by anyone, rewrite it.

<Readability Standard>
========================
READABILITY STANDARD — TARGET SCORES
========================
Make the content highly readable and easy to scan:

- Use short sentences (max 20 words)
- Keep paragraphs 2–4 sentences only
- Break long paragraphs into smaller ones
- Use clear H2 and H3 headings frequently
- Add bullet points for lists and steps
- Use simple, everyday language (avoid jargon)
- Use active voice
- Add examples where helpful
- Highlight key points using bold
- Ensure proper spacing and clean structure
- Start every sentence with a different word than the previous one

The content should be easy to skim and understand within seconds.
</Readability Standard>

HOW TO HIT THESE SCORES — CONCRETE RULES:

SENTENCE LENGTH:
- Target 15–20 words per sentence on average
- Never write a sentence longer than 35 words — split it
- Never start two consecutive sentences with the same word
- Keep sentences over 20 words to under 1 in every 4 (25%) across the whole article — this is Yoast's exact green-light threshold for sentence length
- After every long sentence, write one that is 8 words or fewer
- Count your words mentally. If a sentence is running long, stop and restart

WORD CHOICE — PREFER SHORT WORDS:
- Replace polysyllabic words wherever a simpler word works:
  "utilise" → "use"       "initiate" → "start"    "demonstrate" → "show"
  "facilitate" → "help"   "implement" → "do"       "methodology" → "method"
  "subsequently" → "then" "approximately" → "about" "requirement" → "need"
- If a technical term is unavoidable, immediately explain it in plain English

PARAGRAPH LENGTH:
- Most paragraphs 2–4 sentences, but let actual length vary unevenly — a 15-word paragraph next to a 100-word one reads human; a row of similarly-sized paragraphs reads machine-generated
- Hard ceiling: never exceed 150 words in a single paragraph — this is Yoast's actual red-flag threshold. Don't treat 150 as a target to approach in every paragraph; most should sit well under it, a few can run close to it, irregularly
- One idea per paragraph — never pack two arguments into one block
- White space is readability: short paragraphs improve Flesch scores directly

SUBHEADING FREQUENCY:
- Hard ceiling: never let more than 250 words of body text pass without a new heading — Yoast flags any stretch over 300 words with no subheading, 250 keeps a safe margin
- This applies to the gap between ANY two consecutive headings, at any level — including the text directly under an H2 before its first H3. A common mistake: writing a long "intro" block under the H2 (400+ words) before the first H3 arrives. That gap is exactly what Yoast measures — treat it the same as any other section
- If an H2 needs a lead-in before its H3s, keep that lead-in short (well under 150 words) — one or two paragraphs, not a mini-essay. If you have more to say before the first subtopic, that's a sign it deserves its own H3, not a longer preamble
- Count as you write: once you're ~200 words past the last heading (of either level), the next natural break must get a subheading
- Don't space headings evenly like a metronome — some sections earn 100 words, others can run closer to 250, based on what the content actually needs
- Every subheading must introduce a distinct, specific idea — never split a paragraph in half just to insert a heading with nothing new to say

SENTENCE STRUCTURE MIX (rough article-wide ratio, NOT a literal repeating formula):
- Roughly: 20% very short (≤ 8 words), 40% medium (15–22 words), 20% complex/clausal (20–30 words), 20% punchy follow-ups (≤ 12 words)
- Do NOT cycle through this as a fixed rotation (short → medium → medium → complex → punchy → repeat) — a mechanical cycle is itself a detectable machine pattern, even though each sentence individually looks varied
- Let the mix land unevenly across the article, the way a real person's rhythm actually drifts — not on a schedule

CLAUSE CONTROL:
- Maximum 2 subordinate clauses per sentence
- Never stack: "which", "that", "because", "although", "while" in the same sentence
- If you need more than one "and" in a sentence, split it into two

FORBIDDEN COMPLEXITY PATTERNS:
- Triple noun stacks: "content marketing strategy implementation" → "how you run content marketing"
- Abstract nominalisations: "the utilisation of" → "using", "the provision of" → "providing"
- Passive voice: keep it under 1 in 10 sentences (10%) across the whole article — this is Yoast's green-light threshold. Default to active voice; passive is fine occasionally when the actor is unknown or unimportant, but never more than once per paragraph
- Jargon chains without plain-English follow-up

CONTENT ACCEPTANCE CRITERIA
========================
{LENGTH_ACCEPTANCE_BLOCK}

- Content Should be Human readable based on above format criteria
- Must be Human Written.

- If all acceptance criteria pass then content should be acceptable.
"""

    CONTENT_SYSTEM_PROMPT_TEMPLATE = """
{PERSONA_BLOCK}

---

{BRAND_VOICE_BLOCK}

---

{AUDIENCE_BLOCK}

---

{OUTLINE_BLOCK}

---

{CONTENT_INSTRUCTIONS}

---

###  HARD STOP — OVERRIDES ALL OTHER INSTRUCTIONS

If search_tool returns a message beginning with " SEARCH LIMIT REACHED", this OVERRIDES every other instruction in this prompt.
You MUST immediately call the structured output tool with the complete article. No more tool calls of any kind. No exceptions.

---

### TOOLS — USAGE LIMITS (STRICT)

**search_tool** — Max **6 calls total**:
- Results return title + URL + content snippet — **cite these URLs directly** since they are verified
- Do NOT call once per fact — batch related questions into one query
- Spread searches across major sections: search for each H2 section that needs a real case study

**generate_image** — Max **1 call total**:
- Call once after searches complete with ARTICLE METADATA (title, summary, content_type, primary_keyword, audience, brand_voice, writing_style, search_intent) — do NOT invent a freeform image prompt
- The Image Planning Pipeline handles composition, art direction, and the final artist prompt
- Returns immediately with `{{"status": "generating"}}` — do NOT wait for a URL
- Do NOT embed any image URL in body_markdown — the image is injected automatically
- Do NOT add an entry to the `images` output field for this image

---

### EXECUTION ORDER — FOLLOW EXACTLY, NO SKIPPING

**Step 1 — Search (2–6 calls)**

Run ALL searches before writing anything. Cover each major section that needs a real case study or stat:
- Query A (required): `[topic] case study results 2026 OR latest year` — real brand/person with measurable outcomes
- Query B (required): `[specific tactic or subtopic from outline] success story before after results` — transformation: problem → action → result
- Query C (required): `[topic] statistics research data 2026 OR latest year` — cited stat or study
- Query D–F (as needed): One query per remaining major section that needs a verified example

QUERY WRITING — get real articles, not homepages:
  BAD: "[topic] tips" — returns homepages, useless
  GOOD: "[company or person name] [topic] case study results 2026"
  GOOD: "[subtopic] success story before after measurable outcome"
  GOOD: "[topic] statistics research data 2026 OR current year"
  Always include: a company/person name OR "case study" OR "statistics" OR "research"
  Never use years beyond 2026

**Step 2 — Extract evidence (MANDATORY — do not skip)**

After ALL searches complete, output this block EXACTLY before writing a single word of the article:

```
EVIDENCE I WILL USE:
- FACT: [copy exact sentence or number from search result CONTENT]
  SOURCE: [exact URL from search result]
  SECTION: [which article section this will appear in]
- FACT: [copy exact sentence or number from search result CONTENT]
  SOURCE: [exact URL from search result]
  SECTION: [which article section this will appear in]
[repeat for every fact/story you plan to use]
```

Rules for this block:
- If a search result CONTENT has no usable facts — write "no usable content" for that result and do NOT use that URL
- Every third-party stat, name, outcome, or case study in the final article MUST appear in this block
- If this block is empty — write the entire article in first-person persona voice with no third-party citations
- This block covers ONLY search_tool citations. It does not govern INTERNAL LINKS or the PRODUCT-LED MENTION block (if present) — those follow their own instructions regardless of what's in this block
- Do NOT begin writing the article until this block is fully written

**Step 3 — Generate image + Write the article**
- Call `generate_image` once with article metadata (title, summary, content_type, keywords, audience, brand_voice, writing_style, search_intent) — do NOT write a freeform image prompt; it returns immediately, do NOT wait for a URL
- Then write the article immediately after — do NOT embed any image URL in body_markdown (image is injected automatically)
- Use ONLY the facts listed in your EVIDENCE block above
- For every fact from your EVIDENCE block, embed an inline markdown link in body_markdown:
  Format: [descriptive anchor text](exact_source_url)
  Example: "...inference throughput nearly doubled [(Tom's Hardware)](https://www.tomshardware.com/exact/path)."
- Do NOT introduce any stat, percentage, name, or company that isn't in your EVIDENCE block
- INTERNAL LINKS are exempt from the search_tool URL restriction — embed every URL from the INTERNAL LINKS TO EMBED section as-is, woven into the most topically relevant sentence (not appended at section end)
- The PRODUCT-LED MENTION (if present in the human message) is also exempt from the search_tool/EVIDENCE restriction — place it once, per its own block's instructions, using only the URL that block provides (or no link if it provides none)
- For any section with no evidence — write a first-person persona observation or anecdote instead (no citation needed)
- Every cited fact must also appear in the `facts` output field with its source_url
- Total tool calls: max 7 (6 search + 1 image call) — stop once limit is reached

Write the full article now. Every third-party claim must have an inline [text](url) citation in body_markdown.

{LENGTH_ENFORCEMENT_BLOCK}
"""

    async def abefore_agent(self, state: REXT, runtime: Runtime) -> dict[str, Any] | None:
        print(f"\n[PersonaInjectionMiddleware] ▶ abefore_agent triggered")
        serp_payload = state.get("serp_payload", {})
        user_id = serp_payload.get("user_id")
        workspace_id = serp_payload.get("workspace_id")
        print(f"  user_id={user_id} workspace_id={workspace_id}")

        content_state = state.get("content") or {}
        outline: Optional[OutlineState] = content_state.get("outline")
        content_type = normalize_content_type(content_state.get("content_type")) or "blog"
        personas = await self._fetch_best_persona(workspace_id, outline)
        brand, brand_voice = await self._fetch_brand_and_voice(workspace_id)
        audience = await self._fetch_best_audience(workspace_id)
        target_word_count = (outline or {}).get("target_word_count", 3000)

        persona_context = build_content_context(
            content_type,
            brand=brand,
            brand_voice=brand_voice,
            author_persona=personas,
            audience=audience,
        )

        internal_links = (outline or {}).get("internal_links") or []
        print(f"  persona: {personas.name if personas else 'None'}")
        print(f"  brand: {brand.brand_name if brand else 'None'}  brand_voice: {'set' if brand_voice else 'None'}")
        print(f"  content_type: {content_type}")
        print(f"  outline: {outline.get('title') if outline else 'None'}")
        print(f"  target_word_count: {target_word_count}")
        print(f"  internal_links: {len(internal_links)} candidate(s) — {[lnk.get('url') for lnk in internal_links]}")

        full_prompt = self._build_full_content_prompt(personas, outline, target_word_count, persona_context)

        # Build a compact persona identity header injected into the HumanMessage.
        # gpt-4o-mini with ToolStrategy follows field descriptions and the user message
        # more reliably than a long system prompt — so the persona name must appear there.
        if personas:
            p_name = str(personas.full_name or personas.name)
            p_title = str(personas.professional_title or "expert")
            p_linkedin: str = str(personas.linkedin_url) if personas.linkedin_url is not None else ""
            linkedin_line = f"\n- LinkedIn: {p_linkedin} — place [Connect with {p_name} on LinkedIn]({p_linkedin}) as the very last line of the article (standalone, no heading)" if p_linkedin else ""
            persona_header = (
                f"╔══════════════════════════════════════════════╗\n"
                f"  AUTHOR IDENTITY — ABSOLUTE NON-NEGOTIABLE\n"
                f"  You ARE: {p_name}, {p_title}\n"
                f"  RULES:\n"
                f"  1. The 'introduction' field MUST contain '{p_name}' by name in the first paragraph\n"
                f"  2. '{p_name}' must appear at least 2 more times in body_markdown\n"
                f"  3. Place an author bio section in the MIDDLE of body_markdown (after 40–60% of content) under a natural experience-focused heading — do NOT use '{p_name}' in the heading (e.g. 'My Experience With This', 'A Bit About My Background', 'My Journey in [Field]') — 2-3 sentence bio{linkedin_line}\n"
                f"  4. Do NOT write as an anonymous expert — you are specifically {p_name}\n"
                f"╚══════════════════════════════════════════════╝\n\n"
            )
        else:
            persona_header = ""

        existing_messages = list(state["messages"])

        # add_messages reducer always APPENDS new messages — it never inserts.
        # To get [SystemMessage, HumanMessage] order: remove existing messages,
        # then append sys_msg first, then HumanMessage with persona_header prepended.
        remove_ops = [RemoveMessage(id=m.id) for m in existing_messages if m.id]
        sys_msg = SystemMessage(content=full_prompt, id="sys-seo-persona-outline")
        reinserted = [
            HumanMessage(content=persona_header + (m.content if isinstance(m.content, str) else ""), id=str(uuid.uuid4()))
            for m in existing_messages
            if isinstance(m, HumanMessage)
        ]

        print(f"✓ Injected full SEO+Persona+Outline prompt ({len(full_prompt)} chars)")
        print(f"[PersonaInjectionMiddleware] ✓ done\n")

        return {"messages": remove_ops + [sys_msg] + reinserted}

    def before_agent(self, state: REXT, runtime: Runtime) -> dict[str, Any] | None:
        # Sync fallback — persona fetch requires async, so this is a no-op.
        # The async hook (abefore_agent) will be used by the agent runtime.
        return None

    def _build_full_content_prompt(
        self,
        personas: Optional[AuthorPersona],
        outline: Optional[OutlineState],
        target_word_count: int = 3000,
        persona_context: Optional[ContentPersonaContext] = None,
    ) -> str:
        persona_context = persona_context or ContentPersonaContext()
        persona_block = self._build_persona_block(personas, persona_context) if personas else ""
        brand_voice_block = self._build_brand_voice_block(persona_context)
        outline_block = self._build_outline_block(outline) if outline else ""
        audiences = (outline or {}).get("target_audience") or []
        audience_block = self._build_audience_block(audiences)

        body_min = target_word_count
        body_buffer = max(200, int(target_word_count * 0.15))
        body_max = body_min + body_buffer
        total_min = target_word_count + 200
        total_max = total_min + body_buffer
        section_min = max(300, int(target_word_count * 0.12))
        subsection_min = max(120, int(target_word_count * 0.05))

        length_acceptance_block = (
            f"WORD COUNT — NON-NEGOTIABLE:\n"
            f"- `introduction` field: minimum 200 words\n"
            f"- `body_markdown` field: {body_min}-{body_max} words — stay within this range\n"
            f"- Combined total: {total_min}-{total_max} words — stay within this range\n"
            f"- Every H2 section: minimum {section_min} words\n"
            f"- Every H3 subsection: minimum {subsection_min} words\n"
            f"- DO NOT submit until you have counted and confirmed the total falls within {total_min}-{total_max} words"
        )

        length_enforcement_block = (
            f"### MANDATORY LENGTH ENFORCEMENT\n"
            f"Your output MUST meet ALL of the following before submitting:\n"
            f"- `introduction`: at least 200 words — write 3–4 full paragraphs, not a single paragraph\n"
            f"- `body_markdown`: {body_min}-{body_max} words — each H2 section must have {section_min}+ words, each H3 must have {subsection_min}+ words\n"
            f"- Total combined length: {total_min}-{total_max} words — do not go meaningfully under or over this range\n\n"
            f"EXPANSION RULES — apply to every section that runs short:\n"
            f"- Add a deeper technical explanation (how it works, why it matters)\n"
            f"- Add a concrete real-world example or case study with numbers\n"
            f"- Add a personal anecdote from the persona (failure, pivot, lesson learned)\n"
            f"- Add a step-by-step breakdown if the concept has stages\n"
            f"- Add a \"common mistakes\" or \"what NOT to do\" block\n"
            f"- Add a comparison (before vs after, method A vs method B)\n\n"
            f"TRIMMING RULE — if a draft runs over {total_max} words: cut filler, redundant transitions, and repeated points before submitting — do not pad, but do not overshoot the range either.\n\n"
            f"Do NOT summarize, do NOT repeat the heading as prose, do NOT pad with filler. Expand with substance.\n\n"
            f"Write the full article now with image and fact links included. Target length: {total_min}-{total_max} words total."
        )

        content_instructions = self.CONTENT_INSTRUCTIONS.format(
            LENGTH_ACCEPTANCE_BLOCK=length_acceptance_block,
        )

        return self.CONTENT_SYSTEM_PROMPT_TEMPLATE.format(
            CONTENT_INSTRUCTIONS=content_instructions,
            PERSONA_BLOCK=persona_block,
            BRAND_VOICE_BLOCK=brand_voice_block,
            OUTLINE_BLOCK=outline_block,
            AUDIENCE_BLOCK=audience_block,
            LENGTH_ENFORCEMENT_BLOCK=length_enforcement_block,
        )

    # ------------------------------------------------------------------
    # DB fetch — persona selected at outline time, fetched here by ID
    # ------------------------------------------------------------------
    async def _fetch_best_persona(self, workspace_id, outline: Optional[OutlineState]) -> Optional[AuthorPersona]:
        selected_id = (outline or {}).get("selected_persona_id")  # type: ignore[union-attr]

        def _sync_fetch():
            db = SyncSessionLocal()
            try:
                if selected_id:
                    from uuid import UUID as _UUID
                    result = db.execute(
                        select(AuthorPersona).where(AuthorPersona.id == _UUID(str(selected_id)))
                    )
                    persona = result.scalar_one_or_none()
                    if persona:
                        return persona
                # Fallback: most recently created persona for this workspace
                result = db.execute(
                    select(AuthorPersona)
                    .where(AuthorPersona.workspace_id == workspace_id)
                    .order_by(AuthorPersona.created_at.desc())
                    .limit(1)
                )
                return result.scalar_one_or_none()
            finally:
                db.close()

        return await asyncio.to_thread(_sync_fetch)

    async def _fetch_brand_and_voice(self, workspace_id) -> tuple[Optional[Brand], Optional[BrandVoice]]:
        """Fetch Brand (identity) + BrandVoice (voice/style) for the workspace.

        Previously BrandVoice was never queried anywhere in content
        generation — only a sliver of Brand identity leaked in via the
        outline's brand_voice_promotion step. This is the fix.
        """
        if not workspace_id:
            return None, None

        def _sync_fetch():
            db = SyncSessionLocal()
            try:
                result = db.execute(
                    select(Brand)
                    .options(joinedload(Brand.voice))
                    .where(Brand.workspace_id == workspace_id)
                )
                brand = result.unique().scalar_one_or_none()
                return (brand, brand.voice if brand else None)
            finally:
                db.close()

        return await asyncio.to_thread(_sync_fetch)

    async def _fetch_best_audience(self, workspace_id) -> Optional[Audience]:
        if not workspace_id:
            return None

        def _sync_fetch():
            db = SyncSessionLocal()
            try:
                result = db.execute(
                    select(Audience)
                    .where(Audience.workspace_id == workspace_id)
                    .order_by(Audience.created_at.desc())
                    .limit(1)
                )
                return result.scalar_one_or_none()
            finally:
                db.close()

        return await asyncio.to_thread(_sync_fetch)

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------
    def _build_persona_block(self, persona: AuthorPersona, context: ContentPersonaContext) -> str:
        return self._format_single_persona(persona, context)

    def _build_brand_voice_block(self, context: ContentPersonaContext) -> str:
        """House voice/style + brand identity — wired into content generation
        for the first time (BrandVoice was previously never fetched here)."""
        voice_fields = context.brand_voice_fields
        brand_fields = context.brand_fields
        if not voice_fields and not brand_fields:
            return ""

        lines = ["## BRAND VOICE — HOUSE STYLE (apply on top of your personal voice above)"]

        if "tone_attributes" in voice_fields:
            tone = voice_fields["tone_attributes"]
            tone = ", ".join(tone) if isinstance(tone, list) else tone
            lines.append(f"- **Tone:** {tone}")
        if "formality_level" in voice_fields:
            lines.append(f"- **Formality:** {str(voice_fields['formality_level']).replace('_', ' ')}")
        if "point_of_view" in voice_fields:
            lines.append(f"- **Point of view:** {str(voice_fields['point_of_view']).replace('_', ' ')}")
        if "sentence_length_preference" in voice_fields:
            lines.append(f"- **Sentence length:** {str(voice_fields['sentence_length_preference']).replace('_', ' ')}")
        if "preferred_terms" in voice_fields:
            subs = voice_fields["preferred_terms"] or []
            rendered = "; ".join(
                f"say \"{t.get('term')}\" not \"{t.get('use_instead_of')}\""
                for t in subs if isinstance(t, dict) and t.get("term")
            )
            if rendered:
                lines.append(f"- **Preferred vocabulary:** {rendered}")
        if "banned_terms" in voice_fields:
            banned = voice_fields["banned_terms"]
            banned = ", ".join(banned) if isinstance(banned, list) else banned
            lines.append(f"- **Never use these words/phrases:** {banned}")
        if "cta_style" in voice_fields:
            lines.append(f"- **Calls-to-action:** {voice_fields['cta_style']}")

        if brand_fields:
            lines.append("")
            lines.append("### Brand Context")
            if "about" in brand_fields:
                lines.append(f"- **About the brand:** {brand_fields['about']}")
            if "selling_position" in brand_fields:
                lines.append(f"- **Unique selling position:** {brand_fields['selling_position']}")
            if "customer_profile" in brand_fields:
                lines.append(f"- **Ideal customer:** {brand_fields['customer_profile']}")
            if "competitors" in brand_fields:
                comp = brand_fields["competitors"]
                comp = ", ".join(comp) if isinstance(comp, list) else comp
                lines.append(f"- **Competitors (for context, do not disparage):** {comp}")
            if "content_pillar" in brand_fields:
                pillars = brand_fields["content_pillar"]
                pillars = ", ".join(pillars) if isinstance(pillars, list) else pillars
                lines.append(f"- **Content pillars:** {pillars}")

        return "\n".join(lines)

    def _format_single_persona(self, persona: AuthorPersona, context: ContentPersonaContext) -> str:
        fields = context.author_persona_fields
        # Name/title stay unconditional — the "write as a specific human"
        # framing is a separate, always-on mechanism (see CONTENT_INSTRUCTIONS'
        # non-negotiable author-identity rules) from how much *supporting*
        # biographical detail (expertise/credentials/bio/etc.) is relevant
        # for this content type.
        name = persona.full_name or persona.name
        title = persona.professional_title or "expert"

        lines = [
            "## YOUR AUTHOR IDENTITY — EMBODY THIS FULLY",
            "",
            f"You ARE **{name}**, {title}.",
            "Do not write about this person — write AS this person, in first person.",
            "",
            "### Who You Are",
        ]

        if name:
            lines.append(f"- **Name:** {name}")
        if persona.professional_title:
            lines.append(f"- **Title:** {persona.professional_title}")
        if "areas_of_expertise" in fields:
            expertise = fields["areas_of_expertise"]
            if isinstance(expertise, list):
                expertise = ", ".join(str(e) for e in expertise)
            lines.append(f"- **Expertise:** {expertise}")
        if "experience_type" in fields:
            lines.append(f"- **Experience basis:** {str(fields['experience_type']).replace('_', ' ')}")
        if "years_of_experience" in fields:
            lines.append(f"- **Years in field:** {fields['years_of_experience']}")
        if "credentials" in fields:
            creds = fields["credentials"] or []
            rendered = ", ".join(
                str(c.get("credential")) for c in creds if isinstance(c, dict) and c.get("credential")
            )
            if rendered:
                lines.append(f"- **Credentials:** {rendered}")
        if "employer" in fields:
            lines.append(f"- **Employer:** {fields['employer']}")

        if "bio" in fields:
            lines += ["", "### Your Background", str(fields["bio"])]

        if "writing_voice" in fields:
            lines += ["", "### Your Voice & Tone", str(fields["writing_voice"])]

        audience_fields = context.audience_fields
        if audience_fields.get("pain_points") or audience_fields.get("goals"):
            lines += ["", "### Your Audience"]
            if audience_fields.get("pain_points"):
                lines.append(f"- **Pain points they face:** {', '.join(audience_fields['pain_points'])}")
            if audience_fields.get("goals"):
                lines.append(f"- **Their goals:** {', '.join(audience_fields['goals'])}")
            if audience_fields.get("behaviors"):
                lines.append(f"- **How they behave:** {', '.join(audience_fields['behaviors'])}")

        lines += [
            "",
            "### REQUIRED: How to Use This Identity in the Article",
            f"- **MANDATORY**: Use your name **{name}** in the first or second paragraph of the introduction",
            f"  Good: \"I'm {name}, and as a {title}, I've spent years...\"",
            f"  Good: \"My name is {name}. In my work as a {title}, I've seen firsthand...\"",
            f"- **MANDATORY**: Mention your name **{name}** at least once more later in the article",
            f"  Good: \"In my opinion as {name}...\" or \"From what I've observed...\"",
            "- Reference your background and expertise when introducing any major claim or recommendation",
            "- Your name and professional identity must be unmistakably present — never anonymous, never generic",
        ]

        if persona.linkedin_url:
            lines += [
                "",
                f"- **LinkedIn:** {persona.linkedin_url} — place [Connect with {name} on LinkedIn]({persona.linkedin_url}) as the very last line of the article, standalone, after all sections including FAQ. No heading, no extra text.",
            ]
        else:
            lines += [
                "",
                f"- **LinkedIn:** NONE — do NOT include any LinkedIn link anywhere for {name}. Do not use LinkedIn URLs from other personas.",
            ]

        return "\n".join(lines)

    def _build_outline_block(self, outline: OutlineState) -> str:
        lines = ["## Approved Content Outline"]

        if outline.get("title"):
            lines.append(f"Title: {outline['title']}")

        if outline.get("brief"):
            lines.append(f"\nBrief:\n{outline['brief']}")

        if outline.get("tone"):
            lines.append(f"\nTone: {outline['tone']}")

        if outline.get("target_audience"):
            audiences = ", ".join(outline["target_audience"])
            lines.append(f"Target audience: {audiences}")

        if outline.get("keywords_to_include"):
            keywords = ", ".join(outline["keywords_to_include"])
            lines.append(f"Keywords to include: {keywords}")
        sections = outline.get("sections") or []
        if sections:
            lines.append("\nSections:")
            for i, section in enumerate(sections, 1):
                lines.append(f"  {i}. {section.get('heading', '')}")
                if section.get("description"):
                    lines.append(f"     {section['description']}")
                key_points = section.get("key_points") or []
                for point in key_points:
                    lines.append(f"     - {point}")
                facts = section.get("facts") or []
                if facts:
                    lines.append(f"     Facts:")
                    for fact in facts:
                        lines.append(f"       • {fact.get('text', '')}")
                        if fact.get("source_url"):
                            lines.append(f"         Source: {fact['source_url']}")

        internal_links = outline.get("internal_links") or []
        if internal_links:
            lines.append(f"\nLINKS TO EMBED — ALL {len(internal_links)} MUST APPEAR IN body_markdown as natural anchor text (see embedding rules above — never label as 'internal' to reader):")
            for lnk in internal_links:
                title = lnk.get("title") or lnk.get("url", "")
                url = lnk.get("url", "")
                lines.append(f"  - [{title}]({url})")

        approved_faqs = extract_outline_faqs(outline)
        if approved_faqs:
            lines.append(f"\nAPPROVED FAQs — ALL {len(approved_faqs)} MUST APPEAR IN a FAQ section at the end of the article, near-verbatim (light rewording for flow is fine, do not invent additional/replacement questions):")
            for faq in approved_faqs:
                lines.append(f"  - Q: {faq['question']}")
                if faq.get("answer"):
                    lines.append(f"    A: {faq['answer']}")

        lines.append("\nUse this outline as a guide, but write naturally and adapt where needed but image and facts links included minimum length should be: 3000 words total. Clearly mention the facts and stats with links.")

        return "\n".join(lines)

    def _build_audience_block(self, audiences: list) -> str:
        if not audiences:
            return ""

        audience_list = "\n".join(f"- {a}" for a in audiences)

        return f"""========================
TARGET AUDIENCE — READ THIS BEFORE THE OUTLINE. IT OVERRIDES HOW YOU INTERPRET EVERY SECTION.
========================
This article is written exclusively for:

{audience_list}

This audience definition is NON-NEGOTIABLE. Everything — the framing, the examples, the search queries, the vocabulary — must be filtered through their lens. The outline below is a structural guide only. You must reinterpret every section heading and key point for THIS specific audience.

REFRAME THE OUTLINE FOR THIS AUDIENCE:
- If a section could be read with a gaming, consumer, or general-public angle — rewrite it for this audience's actual use case
- Example: "GTX 1650 vs RTX 3050 performance" for AI Engineers means CUDA cores, VRAM for model training/inference, PyTorch/TensorFlow benchmarks — NOT Cyberpunk or gaming FPS
- Every concrete example, benchmark, or case study must be one THIS audience would encounter in their actual work

SEARCH QUERIES — AUDIENCE-FIRST:
- Always include the audience type in your search queries
- BAD: "[product] performance benchmarks" — returns consumer/gaming results
- GOOD: "[product] [audience role] use case results 2025 OR 2026" — returns relevant results
- GOOD: "[product] [audience-specific metric] performance" — e.g. "GTX 1650 machine learning inference benchmark" for ML Engineers

FOR THIS AUDIENCE, SPECIFICALLY:
- Use their exact vocabulary and domain-specific terminology
- Reference tools, frameworks, workflows, and metrics they use daily in their role
- Name their real pain points — the specific bottlenecks and frustrations of their work context
- Ground every how-to step in their actual environment — not a generic "business owner" or consumer
- Connect outcomes to metrics they care about — not vanity metrics, but the KPIs their role is measured on

DO NOT write generic content and tag the audience name onto it. If a reader from this audience read the article and felt it was written for someone else — it has failed.

If multiple audiences are listed and their needs diverge significantly for a section, call it out: "For [Audience A]... For [Audience B]..."
========================"""
