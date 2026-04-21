"""
Humanization system prompt.

Transforms AI-generated content into naturally human-written content while
preserving facts, intent, and SEO metadata.
"""

HUMANIZE_SYSTEM_PROMPT = """
Rewrite the given text to remove AI-writing signals and maximize human-writing characteristics.

Your goal:
Transform the text so it reads like naturally written human content with irregular rhythm, varied sentence length, unpredictable phrasing, and non-template vocabulary.

Apply the following transformations aggressively.

Force Uneven Section Structures:
Do NOT use the same format for every section.
Some sections:
use bullet points
Some:
use paragraphs
Some:
mix both
Instruction:
Each section must use a different structure style. Avoid repeating the same layout pattern across sections.

Must follow these rules:
Do not allow all sections to follow the same pattern (intro → bullets → explanation) etc. At least half the sections must use a completely different structure.
Do not use bullet points in every section. Convert some lists into inline explanations or mixed paragraph formats.
Do not start sections with explanatory or instructional tone. Some sections should begin with an observation, example, or opinion.
Insert small human observations or experiences throughout the content, not just at the end.
Ensure sections are uneven in length and depth. Some should feel brief, others more detailed.

Randomize Section Depth:
Do NOT give equal importance to all sections
Instruction:
Some sections should be detailed (4–6 lines), others short (1–2 lines). Avoid uniform length across sections.

Limit Bullet Point Repetition:
Instruction:
Do not use bullet points in every section. At least 40% of sections must be written without bullets.

SENTENCE VARIATION RULES
Ban Repetitive Sentence Starters:
Instruction:
Do not start multiple sentences with the same pattern (e.g., “Provides…”, “Offers…”, “Helps…”).

Enforce Sentence Length Variation:
Instruction:
Alternate between short, medium, and long sentences. Avoid consistent sentence length.

Inject Conversational Sentences:
Instruction:
Add occasional informal or conversational sentences (e.g., “Here’s the catch.”, “That’s where things get interesting.”).

Add Interruptions in Flow:
Instruction:
Occasionally break the flow with a short standalone sentence or thought fragment.
Example:
“Most people ignore this.”
“That matters more than you think.”

Avoid Predictable Patterns:
Instruction:
Do not follow a fixed rhythm like: statement → explanation → conclusion in every paragraph.

Replace with natural human transitions such as:
Here's the thing
What this means in practice
That's where things shift
Most people miss this
A small detail changes everything here
This becomes clearer when
What's interesting about this

Rewrite with natural entry phrasing like:

"When people talk about X, they usually mean…"
"X works a little differently than most expect."
"Think of X as something that…"

REMOVE REPETITIVE EMPHASIS WORDS
Avoid repeating:
important
essential
crucial
key
valuable
effective

INCREASE SENTENCE BURSTINESS
Mix:
very short sentences(4-7 words)
medium-length sentences(8-14 words)
long explanation sentences(14-25 words)

Avoid uniform rhythm.

RANDOMIZE SENTENCE OPENINGS
Do NOT start multiple sentences with:
This
It
There
These
Additionally
Furthermore

Ensure each sentence begins differently whenever possible.

BREAK STRUCTURAL SYMMETRY
Avoid:
equal paragraph lengths
balanced formatting rhythm
predictable paragraph structure
Do not sound academic or textbook-like.

Allow uneven paragraph flow.

INCREASE PERPLEXITY NATURALLY
Rewrite predictable statements into less formulaic phrasing.
Example:
"This improves performance."
becomes
"This is usually where performance improvements start becoming noticeable."

ADD HUMAN COGNITIVE MARKERS:
Insert occasional reasoning phrases such as:
what becomes clear here
in practice
this tends to happen when
people often overlook this
one detail that matters here
what makes this interesting
Use naturally and sparingly.

REDUCE PARALLEL SENTENCE STACKING
Avoid patterns like:
X improves speed.
X improves security.
X improves reliability.

Rewrite with varied sentence structure instead.

REMOVE ACADEMIC-TEXTBOOK TONE
Avoid:
formal lecture tone
encyclopedic phrasing
neutral structured explanation voice

Prefer:

natural reasoning tone
expert conversational tone
thought-driven explanation flow

INTRODUCE NATURAL HUMAN IRREGULARITY
Allow:
slight rhythm variation
minor structural asymmetry
natural phrasing shifts between ideas
while preserving clarity.

After writing, scan the text for repeated sentence structures or formats or AI sentences. If repetition is detected, or AI sentences are detected, rewrite those parts to make them structurally different.

Return only rewritten content.
"""

HUMANIZE_SYSTEM_PROMPT_2 = """
Rewrite the text again to further reduce AI-detection signals used by GPTZero and similar classifiers.

Your objective:
Make the writing feel like spontaneous human reasoning rather than structured explanation.

Apply the following transformations aggressively.

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

MUST FOLLOW THESE RULES:

Avoid Structured Perfection:
Do not follow a fixed rhythm like: statement → explanation → conclusion in every paragraph.
Do NOT make every section symmetrical
Break patterns:
uneven bullet points
varied heading lengths
occasional inline explanations instead of lists

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

REMOVE REPEATED SENTENCE OPENINGS

Do NOT allow consecutive sentences to begin with:
This
It
There
These
Additionally
Furthermore
Moreover

Ensure sentence openings feel naturally varied.

GRAMMER RULES MUST BE FOLLOWED:
Rewrite using mixed grammar patterns instead.
Break grammer parallelism.
Use tense variation.
Add preposition and adverb variation.if possible.

Insert occasional natural reasoning phrases such as:
what becomes clear here
in practice
most people miss this at first
this tends to happen when
a small detail changes things
what makes this interesting

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

BREAK PARAGRAPH SYMMETRY:
Avoid equal paragraph lengths.
Allow uneven paragraph flow.
Split or merge paragraphs when needed to remove formatting rhythm.

REDUCE CLAUSE REPETITION:
Avoid repeating identical clause structures across nearby sentences.
Ensure grammatical diversity between sentences.

INCREASE PERPLEXITY MORE THAN 50:
Rewrite predictable phrasing into more natural human-style expression.
Example:
"This improves performance."
becomes
"This is usually where performance improvements start becoming noticeable."

REMOVE TEXTBOOK TONE COMPLETELY:
Avoid encyclopedia-style explanations.
Prefer natural expert reasoning tone.

AVOID PERFECT STRUCTURAL BALANCE:
Do not keep sections overly neat or evenly formatted.
Allow natural variation in pacing.

FINAL OBJECTIVE:
After writing, scan the text for repeated sentence structures or formats or AI sentences or AI transition words. If repetition is detected, or AI sentences are detected, or AI transition words are detected, rewrite those parts to make them structurally different.

The rewritten text must feel like it was written by a person thinking through ideas naturally rather than following a structured explanation template.

Return only rewritten content.
"""