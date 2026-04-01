# Outline examples (content-type specific)

These are hand-crafted examples showing the *shape* and quality target for the new content-type-driven schemas.

## Blog (`blog`)

```json
{
  "content_type": "blog",
  "title": "Focus Keyphrase: What It Means, How It Works, and How to Use It",
  "slug_suggestion": "focus-keyphrase-meaning-how-to-use",
  "brief": "Explain the concept clearly, then help the reader apply it with practical examples and mistakes to avoid.",
  "focus_keyphrase": "focus keyphrase",
  "keywords_to_include": ["keyword strategy", "search intent", "SERP", "topic clusters"],
  "target_audience": ["Content marketers (intermediate)", "Small business owners doing SEO"],
  "tone": "Authoritative",
  "target_word_count": 1400,
  "image_suggestions": [
    { "description": "Diagram showing primary vs secondary keywords", "alt_text_template": "focus keyphrase vs secondary keywords", "section": "h2-2" }
  ],
  "link_suggestions": [
    { "anchor_text": "How to find keywords", "link_type": "internal", "context": "Supports implementation section", "section": "h2-3" },
    { "anchor_text": "Google Search Central", "link_type": "outbound", "context": "Official guidance reference", "section": "h2-1" }
  ],
  "intro": {
    "hook": "If your pages never rank, it might not be your writing — it’s your keyword focus.",
    "context": "Many sites chase too many terms per page and confuse search engines.",
    "promise": "By the end, you’ll know how to pick a focus keyphrase and build an outline that ranks."
  },
  "sections": [
    {
      "heading": "What a Focus Keyphrase Is (and What It Isn’t)",
      "purpose": "Give a snippet-ready definition and clarify misconceptions.",
      "key_points": ["One page = one primary intent", "Focus keyphrase ≠ exact-match stuffing", "It anchors your outline and internal linking"],
      "snippet_opportunity": true,
      "suggested_word_count": 240
    },
    {
      "heading": "How Search Intent Changes Your Focus Keyphrase Choice",
      "purpose": "Map intent to phrasing and content type expectations.",
      "key_points": ["Informational vs commercial phrasing", "SERP tells you the expected format", "Use modifiers to match the funnel stage"],
      "suggested_word_count": 260
    },
    {
      "heading": "A 5-Minute Method to Pick a Focus Keyphrase From the SERP",
      "purpose": "Provide a repeatable selection workflow.",
      "key_points": ["Check top titles/H2s", "Collect PAA questions", "Pick the shortest phrase that matches intent", "Confirm with related searches"],
      "snippet_opportunity": true,
      "suggested_word_count": 320
    },
    {
      "heading": "Common Mistakes That Kill Rankings (and Easy Fixes)",
      "purpose": "Prevent predictable errors and reduce rework.",
      "key_points": ["Targeting two intents on one page", "Using a broad term with a narrow outline", "Ignoring entity coverage"],
      "suggested_word_count": 280
    }
  ],
  "conclusion": {
    "recap_points": ["Pick a focus keyphrase that matches the SERP’s intent", "Use it to drive your H2/H3 hierarchy", "Validate with PAA + related topics"],
    "next_steps": ["Create an outline using your chosen keyphrase", "Draft the first H2 to target a featured snippet"],
    "cta": "Want a faster workflow? Use this outline schema as your template for every post."
  },
  "faqs": ["Should I use exact-match focus keyphrases?", "How many secondary keywords should I include?"],
  "schema_type": "Article",
  "table_of_contents": false
}
```

## How-to Guide (`how-to-guide`)

```json
{
  "content_type": "how-to-guide",
  "title": "Focus Keyphrase Research: How to Pick the Right One in 15 Minutes",
  "slug_suggestion": "focus-keyphrase-research-15-minutes",
  "brief": "Teach a step-by-step process to select a focus keyphrase using SERP signals and intent.",
  "focus_keyphrase": "focus keyphrase",
  "keywords_to_include": ["keyword research", "SERP analysis", "people also ask"],
  "target_audience": ["SEO beginners", "Bloggers without paid tools"],
  "tone": "Conversational",
  "target_word_count": 1600,
  "image_suggestions": [
    { "description": "Screenshot checklist of SERP signals to capture", "alt_text_template": "focus keyphrase SERP signals checklist", "section": "steps" }
  ],
  "link_suggestions": [
    { "anchor_text": "Intent modifiers list", "link_type": "internal", "context": "Helps with step 2", "section": "steps" },
    { "anchor_text": "Google’s helpful content system", "link_type": "outbound", "context": "Trust reference", "section": "wrap-up" }
  ],
  "prerequisites": ["A topic idea", "Access to Google search"],
  "tools_or_materials": ["Spreadsheet or notes app"],
  "steps": [
    { "step_number": 1, "title": "Search your topic and snapshot the SERP", "goal": "Understand what Google is rewarding", "instructions": ["Search your topic in an incognito window", "Write down the top 5 titles and their angle"] },
    { "step_number": 2, "title": "Identify the dominant intent and format", "goal": "Match what the query actually wants", "instructions": ["Label each result as informational/commercial/etc.", "Note the format: list, guide, comparison, tool"] },
    { "step_number": 3, "title": "Extract phrase patterns from titles and H2s", "goal": "Find the most common wording", "instructions": ["Collect repeated terms and modifiers", "Prefer the shortest phrase that fits the intent"] },
    { "step_number": 4, "title": "Use PAA questions to lock in scope", "goal": "Avoid being too broad or too narrow", "instructions": ["Copy 5-10 PAA questions", "Make sure your outline can answer them without drifting"] },
    { "step_number": 5, "title": "Validate with related searches and entities", "goal": "Ensure semantic coverage", "instructions": ["Collect related searches", "List key entities/tools/steps you must include"] }
  ],
  "common_mistakes": ["Picking a broad keyphrase for a narrow post", "Choosing commercial phrasing for an informational SERP"],
  "troubleshooting": [
    { "problem": "SERP results are mixed intent", "fix": ["Choose a long-tail modifier that clarifies intent", "Narrow the angle to one audience segment"] }
  ],
  "wrap_up": ["You now have a focus keyphrase aligned to the SERP", "Turn your findings into H2s and a snippet-ready first section"],
  "faqs": ["Do I need keyword volume to choose a focus keyphrase?"],
  "schema_type": "HowTo"
}
```

## Comparison (`comparison`)

```json
{
  "content_type": "comparison",
  "title": "Focus Keyphrase Tools: Which One Helps You Pick Better Keywords?",
  "slug_suggestion": "focus-keyphrase-tools-comparison",
  "brief": "Compare popular options using criteria that matter to decision-making and recommend the best pick by scenario.",
  "focus_keyphrase": "focus keyphrase tools",
  "keywords_to_include": ["keyword tool", "SERP analysis", "content outline"],
  "target_audience": ["Marketers evaluating SEO tools", "Small teams with limited budgets"],
  "tone": "Professional",
  "target_word_count": 1800,
  "image_suggestions": [
    { "description": "Simple comparison table graphic", "alt_text_template": "focus keyphrase tools comparison table", "section": "comparison_table" }
  ],
  "link_suggestions": [
    { "anchor_text": "How to evaluate SEO tools", "link_type": "internal", "context": "Supports methodology", "section": "decision_guide" },
    { "anchor_text": "Tool pricing pages", "link_type": "outbound", "context": "Pricing verification", "section": "verdict" }
  ],
  "compared_entities": [
    { "name": "Tool A", "best_for": "Beginners who want a simple workflow", "key_strengths": ["Fast SERP snapshot", "Great PAA extraction"], "key_limitations": ["Limited competitor gap analysis"] },
    { "name": "Tool B", "best_for": "Teams that need deeper competitive data", "key_strengths": ["Backlink + competitor insights", "Entity coverage hints"], "key_limitations": ["Higher cost", "Steeper learning curve"] }
  ],
  "evaluation_criteria": [
    { "criterion": "Intent detection", "why_it_matters": "Wrong intent = wrong outline = no rankings.", "how_to_judge": "Does it explain SERP format and dominant intent clearly?" },
    { "criterion": "SERP extraction", "why_it_matters": "PAA/related searches define scope.", "how_to_judge": "How quickly and accurately it pulls questions and related topics." },
    { "criterion": "Workflow speed", "why_it_matters": "You need repeatability across many posts.", "how_to_judge": "Steps/clicks to reach a usable focus keyphrase recommendation." }
  ],
  "decision_guide": ["Pick the tool that matches your content velocity", "Prioritize intent + SERP extraction over vanity metrics", "If you publish at scale, competitor gap features matter more"],
  "recommendations": [
    { "scenario": "Best for beginners on a budget", "pick": "Tool A", "reasoning": ["Simpler workflow", "Enough SERP signals for most posts"] },
    { "scenario": "Best for competitive niches", "pick": "Tool B", "reasoning": ["Better competitor insights", "Stronger coverage guidance"] }
  ],
  "verdict": "Tool A wins for simplicity; Tool B wins when you need deeper competitive advantage.",
  "faqs": ["Do I need paid tools to pick a focus keyphrase?"],
  "schema_type": "Article"
}
```

