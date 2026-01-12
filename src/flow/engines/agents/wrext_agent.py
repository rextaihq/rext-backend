"""
WREXT Multi-Agent System

A supervisor agent that coordinates content generation and E-E-A-T enhancement
using specialized sub-agents.

Architecture:
- Supervisor Agent: Orchestrates the workflow
- Generator Agent: Creates initial content based on outline
- E-E-A-T Agent: Enhances content with experience, expertise, authoritativeness, and trustworthiness signals
"""

from langchain.agents import create_agent
from langchain.tools import tool
from src.flow.model.llm_manager import load_model
from src.flow.states.wrext import WREXT
from src.flow.engines.agents.generator.generator import writer_agent
from src.flow.engines.agents.generator.eeat import eeat_agent
from src.flow.model.structure.content import GeneratedContent
from langchain.agents.structured_output import ToolStrategy


# Supervisor System Prompt
SUPERVISOR_PROMPT = """
You are a content production supervisor managing a team of specialized agents.

## YOUR TEAM

1. **Content Generator** (`generate_content` tool)
   - Creates initial article drafts based on outlines
   - Follows SEO best practices
   - Produces structured, well-researched content

2. **E-E-A-T Enhancer** (`enhance_with_eeat` tool)
   - Takes generated content and enriches it with authenticity
   - Adds experience, expertise, authoritativeness, and trustworthiness signals
   - Makes content sound like it's written by a real expert

## YOUR WORKFLOW

When the user requests content creation:

1. **First, generate the base content**
   - Use the `generate_content` tool with the outline
   - This creates the initial article structure and information

2. **Then, enhance with E-E-A-T signals**
   - Take the generated content from step 1
   - Use the `enhance_with_eeat` tool to inject authenticity
   - This adds real-world experience and expert perspective

3. **Return the final enhanced content**
   - The E-E-A-T enhanced version is the final output

## IMPORTANT RULES

- Always use BOTH agents in sequence: generate first, then enhance
- Pass the full generated content to the E-E-A-T agent
- Don't skip steps - both are essential for high-quality output
- Coordinate the workflow smoothly without user intervention

## EXAMPLE WORKFLOW

User: "Create an article about programmatic SEO"

You should:
1. Call `generate_content` with the outline
2. Take the result and call `enhance_with_eeat` with that content
3. Return the final E-E-A-T enhanced article

Now coordinate the content production workflow.
"""


@tool
def generate_content(request: str) -> str:
    """
    Generate initial content based on an outline.
    
    Use this tool when you need to create the base article from an outline.
    This produces well-structured, SEO-optimized content.
    
    Input: Natural language request with outline information
    Example: "Generate content for the programmatic SEO outline"
    
    Returns: Generated article with title, body, keywords, and metadata
    """
    print("\n🔨 GENERATOR AGENT: Creating base content...")
    
    # Invoke the generator agent
    result = writer_agent.invoke({
        "messages": [{"role": "user", "content": request}]
    })
    
    # Extract the generated content
    # generated = result["messages"][-1].content
    
    print("✅ GENERATOR AGENT: Content created successfully")
    return result["messages"][-1].text


@tool
def enhance_with_eeat(request: str) -> str:
    """
    Enhance generated content with E-E-A-T signals.
    
    Use this tool AFTER generating content to add authenticity, experience,
    and expert perspective to the article.
    
    Input: The generated content from the generator agent (as a string)
    Example: Pass the full output from generate_content
    
    Returns: Enhanced article with E-E-A-T signals injected
    """
    print("\n✨ E-E-A-T AGENT: Enhancing content with authenticity...")
    
    # Invoke the E-E-A-T agent
    result = eeat_agent.invoke({
        "messages": [{
            "role": "user",
            "content": f"Here's the generated content to enhance:\n\n{request}\n\nInject E-E-A-T signals to make it authentic and experience-driven."
        }]
    })
    
    # Extract the enhanced content
    # enhanced = result["messages"][-1].content
    
    print("✅ E-E-A-T AGENT: Content enhanced successfully")
    return result["messages"][-1].text


# Create the supervisor agent
wrext_supervisor = create_agent(
    model=load_model(),
    tools=[generate_content, enhance_with_eeat],
    system_prompt=SUPERVISOR_PROMPT,
    state_schema=WREXT,
    response_format=ToolStrategy(GeneratedContent),
    debug=True
)


if __name__ == "__main__":
    from src.flow.states.content import ContentOutline
    from src.flow.engines.content.generation.eeat_injection import get_eeat_persona
    
    # Get E-E-A-T persona
    eeat_persona = get_eeat_persona()
    
    # Sample outline for testing
    test_outline: ContentOutline = {
        "title": "Complete Guide to Programmatic SEO: Scale Your Content Strategy",
        "brief": "A practical guide to implementing programmatic SEO for scaling content production, based on real-world experience with 100k+ page websites.",
        "sections": [
            {
                "heading": "What is Programmatic SEO and Why It Matters",
                "description": "Understanding the fundamentals and real-world applications",
                "key_points": [
                    "Definition and core concepts",
                    "When programmatic SEO makes sense (and when it doesn't)",
                    "Real examples from B2B SaaS and content-heavy sites"
                ],
                "suggested_word_count": 400
            },
            {
                "heading": "Building Your Programmatic SEO Infrastructure",
                "description": "Technical setup and data pipeline architecture",
                "key_points": [
                    "Data sources and collection strategies",
                    "Template design and dynamic content generation",
                    "AI-assisted content pipelines vs. pure templates",
                    "Common pitfalls from actual implementations"
                ],
                "suggested_word_count": 600
            },
            {
                "heading": "Quality Control and Avoiding Thin Content",
                "description": "Ensuring your programmatic pages add real value",
                "key_points": [
                    "Google's stance on programmatic content",
                    "Quality signals that matter",
                    "Content auditing at scale",
                    "Balancing automation with uniqueness"
                ],
                "suggested_word_count": 500
            }
        ],
        "target_audience": ["SEO professionals", "Marketing managers", "SaaS founders"],
        "tone": "conversational and direct, mixes casual and professional tone",
        "keywords_to_include": [
            "programmatic SEO",
            "technical SEO",
            "content automation",
            "AI-assisted content"
        ],
        "status": "approved",
        "rejected_reason": None
    }
    
    # Construct the state
    dummy_state: WREXT = {
        "content": {
            "outline": test_outline,
            "topics": [],
            "selected_topic": "",
            "draft": {},
            "review": {},
            "final_content": {},
            "status": "generating",
            "outline_retries": 0,
            "draft_retries": 0,
            "review_retries": 0,
            "max_retries": 3,
            "error": None,
        }
    }
    
    print("="*80)
    print("🚀 WREXT MULTI-AGENT SYSTEM")
    print("="*80)
    print(f"\nPersona: {eeat_persona['name']} - {eeat_persona['role']}")
    print(f"Outline: {test_outline['title']}")
    print(f"Sections: {len(test_outline['sections'])}")
    print("\n" + "="*80)
    print("STARTING WORKFLOW...")
    print("="*80)
    
    # Invoke the supervisor
    input_state = dummy_state.copy()
    input_state["messages"] = [{
        "role": "user",
        "content": f"Create a complete article based on this outline: {test_outline}."
    }]
    
    result = wrext_supervisor.invoke(input_state)
    
    print("\n" + "="*80)
    print("📄 FINAL OUTPUT")
    print("="*80)
    print(result["messages"][-1].content)
