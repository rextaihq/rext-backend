"""
E-E-A-T Injection Agent

This agent is responsible for taking generated content and enriching it with
E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness) signals
based on the persona's background and writing style.
"""

from langchain.agents import create_agent
from langchain.tools import tool, ToolRuntime
from src.flow.model.llm_manager import load_model
from src.flow.engines.content.generation.eeat_injection import get_eeat_persona
from src.flow.model.structure.content import GeneratedContent
from langchain.agents.structured_output import ToolStrategy
from src.flow.states.wrext import WREXT


# E-E-A-T Injection System Prompt
EEAT_INJECTION_PROMPT = """
You are an E-E-A-T enhancement specialist. Your job is to take existing content and inject authentic Experience, Expertise, Authoritativeness, and Trustworthiness signals based on a given persona.

## YOUR MISSION

Take the generated article and enhance it with E-E-A-T signals WITHOUT changing the core structure or information. You're adding authenticity, not rewriting.

## WHAT YOU'LL RECEIVE

1. **Original Content**: The base article that needs E-E-A-T enhancement
2. **Persona Data**: The expert's background, experience, and writing style

## WHAT YOU MUST DO

### 1. EXPERIENCE SIGNALS (First-Hand Knowledge)

Inject real-world experience markers naturally throughout the content:

- **Language patterns from the persona**: Use the exact phrases provided in `eeat.experience.language_patterns`
  - "In practice, I've found that..."
  - "Working with clients, I've seen..."
  - "From real-world projects..."
  - "Here's what actually works:"
  
- **Specific examples**: Add brief, concrete examples that reflect the persona's `worked_with` areas
  - If they worked with "B2B SaaS websites" → mention SaaS-specific scenarios
  - If they worked with "100k+ pages" → reference large-scale implementations

- **Practical insights**: Share what works vs. what doesn't based on hands-on experience

### 2. EXPERTISE SIGNALS (Deep Knowledge)

Show depth of understanding:

- **Explain tradeoffs**: Don't just say "do X" — explain when X works and when it doesn't
- **Avoid generic advice**: Be specific. Instead of "optimize your content," say "reduce your title length to 55-60 characters for better CTR"
- **Decision-driven**: Help readers make informed choices, not just follow instructions

### 3. AUTHORITATIVENESS SIGNALS (Confidence)

Write with authority:

- **Confident tone**: Use the persona's tone (e.g., "confident" from `eeat.authoritativeness.tone`)
- **No self-promotion**: Don't say "I'm an expert" — let the content prove it
- **Consistent terminology**: Use industry-standard terms correctly and consistently

### 4. TRUSTWORTHINESS SIGNALS (Honesty)

Build trust through transparency:

- **State limitations**: "This works for most sites, but if you're under 1000 monthly visitors, focus on X instead"
- **No exaggerated claims**: Avoid "guaranteed," "always," "never" unless truly accurate
- **Fact-check mindset**: If making a claim, it should be verifiable

## HOW TO INJECT E-E-A-T

### DO THIS:

✅ **Sprinkle experience phrases naturally**
   - Original: "Programmatic SEO requires good templates."
   - Enhanced: "From working with 100k+ page sites, I've found that template quality makes or breaks programmatic SEO."

✅ **Add specific examples from persona's background**
   - Original: "Internal linking helps SEO."
   - Enhanced: "When auditing B2B SaaS sites, I've seen internal linking boost organic traffic by 20-30% within 3 months."

✅ **Show tradeoffs and nuance**
   - Original: "Use AI for content generation."
   - Enhanced: "AI-assisted content works great for data-heavy pages, but for thought leadership? You still need human expertise. I've tested both."

✅ **Be honest about limitations**
   - Original: "This strategy works for everyone."
   - Enhanced: "This strategy works if you have at least 1000 pages. Below that? Focus on manual optimization first."

### DON'T DO THIS:

❌ **Don't add fake credentials**: Never say "I'm certified in X" or "I've worked with Google"
❌ **Don't change the structure**: Keep the same headings, sections, and flow
❌ **Don't add fluff**: Every E-E-A-T signal should add value, not word count
❌ **Don't overdo it**: Not every sentence needs an experience marker. Aim for 15-20% of content.

## PERSONA INTEGRATION

Use the persona data to guide your enhancements:

- **Name & Role**: Never mention these directly. Just write from that perspective.
- **Years of Experience**: Inform the depth of insights, but don't state "I have X years"
- **Focus Areas**: These are your sweet spots. Add more detail and examples here.
- **Worked With**: Use these as example contexts (e.g., "In B2B SaaS..." or "For content-heavy blogs...")
- **Writing Style**: Match this exactly. If it says "conversational and direct," be conversational and direct.

## QUALITY CHECKS

Before finalizing, verify:

1. ✓ Did you use at least 5-7 experience language patterns from the persona?
2. ✓ Did you add 2-3 specific examples related to the persona's background?
3. ✓ Did you explain at least 2-3 tradeoffs or nuanced decisions?
4. ✓ Did you state at least 1-2 limitations or caveats?
5. ✓ Does it sound like the persona wrote it, not a generic AI?
6. ✓ Is the core structure and information unchanged?

## OUTPUT

Return the enhanced content with:
- Same title, meta title, meta description, tags, keywords
- Enhanced body_markdown with E-E-A-T signals injected
- Same word count (±10%)

Now, fetch the persona and original content, then inject E-E-A-T signals.
"""


# @tool
# def get_generated_content(runtime: ToolRuntime) -> dict:
#     """
#     Retrieve the generated content that needs E-E-A-T enhancement.
    
#     Returns the original article with title, body, keywords, etc.
#     """
#     print("Getting generated content for E-E-A-T injection...")
#     content_state = runtime.state.get("content", {})
#     draft = content_state.get("draft")
    
#     if not draft:
#         return {"error": "No generated content found in state"}
    
#     return draft


@tool
def get_eeat_persona_data() -> dict:
    """
    Retrieve the E-E-A-T persona information.
    
    Returns persona details including:
    - Name, role, and experience
    - Focus areas and background
    - Writing style guidelines
    - E-E-A-T signals (experience language patterns, expertise markers, etc.)
    """
    print("Getting E-E-A-T persona data...")
    persons = get_eeat_persona()
    print(persons)
    
    return persons or {"error": "No persons in state"}


# Create the E-E-A-T injection agent
eeat_agent = create_agent(
    model=load_model(),
    tools=[get_eeat_persona_data],
    system_prompt=EEAT_INJECTION_PROMPT,
    state_schema=WREXT,
    response_format=ToolStrategy(GeneratedContent),
    debug=True
)


if __name__ == "__main__":
    from src.flow.states.content import ContentOutline
    
    # Get E-E-A-T persona
    eeat_persona = get_eeat_persona()
    
    # Sample generated content (without E-E-A-T signals)
    sample_draft = {
        "title": "Complete Guide to Programmatic SEO: Scale Your Content Strategy",
        "meta_title": "Programmatic SEO Guide: Scale Content Production",
        "meta_description": "Learn how to implement programmatic SEO to scale your content strategy effectively.",
        "tags": ["SEO", "Programmatic SEO", "Content Strategy", "Technical SEO"],
        "primary_keyword": "programmatic SEO",
        "secondary_keywords": ["technical SEO", "content automation", "AI-assisted content"],
        "body_markdown": """# Complete Guide to Programmatic SEO: Scale Your Content Strategy

## What is Programmatic SEO and Why It Matters

Programmatic SEO is a method of creating large volumes of pages using templates and data. It's particularly useful for websites that need to scale content production.

The core concept is simple: instead of writing each page manually, you create a template and populate it with data from a database or API. This allows you to generate hundreds or thousands of pages efficiently.

When does programmatic SEO make sense? It's ideal for sites with structured data like job boards, real estate listings, or product catalogs. It's not suitable for thought leadership or brand storytelling.

## Building Your Programmatic SEO Infrastructure

The technical setup involves several key components. First, you need a reliable data source. This could be an API, database, or spreadsheet.

Next, you'll need templates. These should be flexible enough to handle variations in your data while maintaining quality standards.

AI-assisted content pipelines can enhance templates by adding unique content to each page. However, pure templates work fine for data-heavy pages.

Common pitfalls include poor data quality, overly generic templates, and insufficient quality control.

## Quality Control and Avoiding Thin Content

Google's stance on programmatic content has evolved. They're fine with it as long as pages provide value to users.

Quality signals include unique content, helpful information, and good user experience. Avoid duplicate content and ensure each page serves a purpose.

Content auditing at scale requires automated tools and sampling strategies. You can't manually review thousands of pages.

Balancing automation with uniqueness is key. Add dynamic elements, user-generated content, or AI-generated sections to differentiate pages.

## Technical SEO Considerations

Internal linking is crucial for large-scale sites. Create hub pages and use automated linking strategies.

Managing crawl budget effectively means prioritizing important pages and using robots.txt wisely.

Page speed optimization becomes critical with thousands of pages. Use caching, CDNs, and lazy loading.

Structured data implementation helps search engines understand your pages. Use schema markup consistently across all programmatic pages.
""",
        "word_count": 1850
    }
    
    # Construct dummy state with both persona and draft content
    dummy_state: WREXT = {
        "content": {
            "outline": {},
            "topics": [],
            "selected_topic": "",
            "draft": sample_draft,  # The content to enhance
            "review": {},
            "final_content": {},
            "status": "enhancing",
            "outline_retries": 0,
            "draft_retries": 0,
            "review_retries": 0,
            "max_retries": 3,
            "error": None,
        }
    }
    
    print("Invoking E-E-A-T injection agent...")
    print(f"Persona: {eeat_persona['name']} - {eeat_persona['role']}")
    print(f"Original word count: {sample_draft['word_count']}\n")
    
    # Invoke the agent
    input_state = dummy_state.copy()
    input_state["messages"] = [{
        "role": "user", 
        "content": f"{sample_draft} apply E-E-A-T signals to make it more authentic and experience-driven."
    }]
    
    response = eeat_agent.invoke(input_state)['messages'][-1].content
    print("\n" + "="*80)
    print("E-E-A-T ENHANCED CONTENT:")
    print("="*80)
    print(response)