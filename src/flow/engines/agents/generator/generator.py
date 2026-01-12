from dataclasses import dataclass
from langchain.agents import create_agent
from langchain.tools import tool, ToolRuntime
from src.flow.model.llm_manager import load_model
from src.flow.prompts.system.content import CONTENT_SYSTEM_PROMPT
from src.flow.engines.content.generation.eeat_injection import get_eeat_persona
from src.flow.model.structure.content import GeneratedContent
from langchain.agents.structured_output import ToolStrategy
from src.flow.states.wrext import WREXT


@tool
def get_outline(runtime: ToolRuntime) -> dict:
    """
    Retrieve the current content outline from the agent state.
    
    Use this to access the approved content outline and its sections.
    """
    print("Getting outline")
    state = runtime.state
    print("State: ", state)
    content_state = runtime.state.get("content", {})
    outline = content_state.get("outline")
    return outline or {"error": "No outline in state"}


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

writer_agent = create_agent(
    model=load_model(),
    tools=[get_outline, get_eeat_persona_data],
    system_prompt=CONTENT_SYSTEM_PROMPT,
    state_schema=WREXT,
    response_format=ToolStrategy(GeneratedContent),
    debug=True
)
 
if __name__ == "__main__":
    from src.flow.states.content import ContentOutline, ContentSection

    dummy_outline: ContentOutline = {
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
            },
            {
                "heading": "Technical SEO Considerations",
                "description": "Crawling, indexing, and performance optimization",
                "key_points": [
                    "Internal linking strategies for large-scale sites",
                    "Managing crawl budget effectively",
                    "Page speed optimization for thousands of pages",
                    "Structured data implementation"
                ],
                "suggested_word_count": 450
            }
        ],
        "target_audience": ["SEO professionals", "Marketing managers", "SaaS founders", "Content strategists"],
        "tone": "conversational and direct, mixes casual and professional tone, gets to the point without fluff",
        "keywords_to_include": [
            "programmatic SEO",
            "technical SEO",
            "content automation",
            "AI-assisted content",
            "large-scale SEO",
            "content pipeline"
        ],
        "status": "approved",
        "rejected_reason": None
    }

    # Construct the dummy WREXT state
    dummy_state: WREXT = {
        "content": {
            "outline": dummy_outline,
            "topics": [],
            "selected_topic": "",
            "draft": {},
            "review": {},
            "final_content": {},
            "status": "drafting",
            "outline_retries": 0,
            "draft_retries": 0,
            "review_retries": 0,
            "max_retries": 3,
            "error": None
        }
    }

    print("Invoking agent with dummy state...")
    # Merge messages into the state
    input_state = dummy_state.copy()
    input_state["messages"] = [{"role": "user", "content": "Fetch the outline and and based on the outline write the article."}]
    
    response = writer_agent.invoke(input_state)['messages'][-1].content
    print("Response:", response)