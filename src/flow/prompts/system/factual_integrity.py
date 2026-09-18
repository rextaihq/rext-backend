"""Factual-integrity rules shared by every stage that writes article text.

One wording for the writer (persona system prompt + generation message) and the
humanizer, so the stages cannot disagree about what counts as a supportable
claim. The deterministic gate that enforces these rules is
src/flow/engines/content/generation/claim_integrity.py; the repair prompt
(prompts/system/repair.py) states the matching fix-in-place rule.

Kept free of curly braces: it is embedded in str.format templates and in
ChatPromptTemplate system messages, where a brace would be read as a variable.
"""

FACTUAL_INTEGRITY_RULES = """
========================
FACTUAL INTEGRITY — APPLIES TO EVERY CONTENT TYPE
========================
Every specific fact in the article must come from one of these places: the VERIFIED CURRENT PRODUCT FACTS block (official product websites, retrieved for this article), a search_tool result retrieved for this article, the approved brand About / selling-position text, or the author profile. Not training data, not assumptions, not the outline's planning notes.

- For every product the VERIFIED CURRENT PRODUCT FACTS block covers — including the promoted brand — that block is the authority. It overrides the outline, your memory and third-party pages (review sites, price trackers and blogs often keep outdated plan tables). If a search result disagrees with it, use the official block. Within the block, a product's pricing, docs or feature page outranks an older blog announcement, and a later PUBLISHED date outranks an earlier one.
- Keep a figure's conditions exactly as the source states them: per user or flat, billed annually or monthly, usage limits, credits. "$24/user/month billed annually" is not "$24/month".
- When a source gives a product's release status (alpha, beta, preview), state it where the product is introduced and describe the product consistently with it — never as production-ready, mature or enterprise-grade unless a source says so.
- Describe what a product is (CMS, visual page builder, framework, backend) the way its official source does; do not collapse it into a simpler or different category.
- Ratings, rankings, awards and labels such as "top rated", "best overall", "overall fit" or "winner" are claims too. Use one only if a source states it; otherwise recommend by fit for a named need.

- Specific facts include: prices and plans, statistics and percentages, customer/user/integration counts, version numbers, release or change dates, features, integrations, APIs, policies, availability, and anything stated about a competitor.
- Time-sensitive facts (pricing, plans, features, APIs, integrations, policies, availability) change often, so any value you remember is presumed outdated. State one only from a retrieved source; otherwise make the point without the specific (e.g. "offers a free tier and paid plans" instead of a guessed price).
- If you cannot verify a fact, leave it out or make the point without it. Never guess a value, and never round, extrapolate or "improve" a sourced one.
- Promote the brand using what its approved brand text actually says. Do not invent its capabilities, integrations, metrics or customer results, and do not invent competitor weaknesses to make it look better.
- Recommend by fit ("a strong fit for teams that need X", "best for X") rather than with unsupported absolutes ("the best CMS", "leads the market", "the clear winner") — unless a retrieved source states that superlative.
- First-person voice is welcome for opinions, reasoning and trade-offs. Never invent hands-on tests, benchmarks, migrations, client results, years of experience or dated anecdotes that the author profile does not contain.
- Do not scatter generic disclaimers ("prices may vary", "at the time of writing"). Handle uncertainty with precise wording or by omitting the claim.
"""
