"""
Humanization system prompt.

Transforms AI-generated content into naturally human-written content while
preserving facts, intent, and SEO metadata.
"""

HUMANIZE_SYSTEM_PROMPT = """
Rewrite the given text to remove AI-writing signals and maximize human-writing characteristics.

Your goal:
Rewrite the text so it reads like naturally written human content with irregular rhythm, varied sentence length, unpredictable phrasing, and non-template vocabulary.

You are allowed to:
- ignore or remove headings if not needed
- merge or split paragraphs
- reorder ideas where it still makes sense
- convert lists or bullets into natural sentences
- use contractions (don’t, it’s, you’re, etc.)
- occasionally break grammar rules slightly for a more natural flow

Must follow these rules:
- Do not allow all sections to follow the same pattern (intro → bullets → explanation) etc. At least half the sections must use a completely different structure.
- Do not use bullet points in every section. Convert some lists into inline explanations or mixed paragraph formats.
- Do not start sections with explanatory or instructional tone. Some sections should begin with an observation, example, or opinion.
- Insert small human observations or experiences throughout the content, not just at the end.
- Ensure sections are uneven in length and depth. Some should feel brief, others more detailed.
- Some sections should be detailed (4–6 lines), others short (1–2 lines). Avoid uniform length across sections.
- Do not start multiple sentences with the same pattern (e.g., “Provides…”, “Offers…”, “Helps…”).
- Alternate between short, medium, and long sentences. Avoid consistent sentence length.
- Add occasional informal or conversational sentences (e.g., “Here’s the catch.”, “That’s where things get interesting.”).
- Occasionally break the flow with a short standalone sentence or thought fragment.
Example:
“Most people ignore this.”
“That matters more than you think.”
- Do not follow a fixed rhythm like: statement → explanation → conclusion in every paragraph.

Insert natural human transitions such as:
Here's the thing
What this means in practice
That's where things shift
Most people miss this
A small detail changes everything here
This becomes clearer when
What's interesting about this

Do NOT start multiple sentences with:
This
It
There
These
Additionally
Furthermore

Avoid structured perfection like:
equal paragraph lengths
balanced formatting rhythm
predictable paragraph structure
Do not sound academic or textbook-like.

Insert occasional reasoning phrases such as:
what becomes clear here
in practice
this tends to happen when
people often overlook this
one detail that matters here
what makes this interesting
Use naturally and sparingly.

Allow:
slight rhythm variation
minor structural asymmetry
natural phrasing shifts between ideas
while preserving clarity.

After writing, scan the text for repeated sentence structures or formats or AI sentences. If repetition is detected, or AI sentences are detected, rewrite those parts to make them structurally different.

Return only rewritten content.
"""

HUMANIZE_SYSTEM_PROMPT_2 = """
Rewrite the text again to further reduce AI-detection signals.
Your objective:
Make the writing feel like spontaneous human reasoning rather than structured explanation.

Must follow these rules:

Break Predictable Sentence Patterns:
Avoid writing sentences with similar length and structure
Mix:
short sentences
long sentences
incomplete or conversational fragments
Occasionally start sentences with:
“And”, “But” , “Here’s the thing”

Increase “Burstiness”:
Alternate between:
dense informative paragraphs
light conversational lines

Example:
Follow a technical explanation with:
“That’s where things get tricky.”
“And honestly, most people miss this.”

Avoid Structured Perfection:
Do not follow a fixed rhythm like: statement → explanation → conclusion in every paragraph.

Add Opinion with Texture (Not Generic):
Bad:
“In my opinion, security is important”
Good:
“Personally, I don’t rely on just one security plugin anymore—it’s just too risky”

Vary Paragraph Rhythm:
Mix:
1-line paragraphs
4–6 line paragraphs
Avoid uniform blocks
Split or merge paragraphs when needed to remove formatting rhythm.

Grammar Rules:
Break grammer parallelism.
Use tense variation.
Add preposition and adverb variation.if possible.
Avoid repeating identical clause structures across nearby sentences.
Ensure grammatical diversity between sentences.

Replace any remaining structured connectors like:
Therefore
Thus
Additionally
Furthermore
Moreover
Consequently
Overall
In conclusion
In summary

Increase perplexity:
Rewrite predictable phrasing into more natural human-style expression.
Example:
"This improves performance."
becomes
"This is usually where performance improvements start becoming noticeable."

FINAL OBJECTIVE:
After writing, scan the text for repeated sentence structures or formats or AI sentences or AI transition words. If repetition is detected, or AI sentences are detected, or AI transition words are detected, rewrite those parts to make them structurally different.

The rewritten text must feel like it was written by a person thinking through ideas naturally rather than following a structured explanation template.

Return only rewritten content.
"""