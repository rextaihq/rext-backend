from typing import Any, Callable, Sequence, Optional
from uuid import UUID
from langchain_core.caches import BaseCache
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langgraph.graph.state import CompiledStateGraph

from src.flow.engines.agent.tools.tools import get_tools
from src.flow.model.structure.content import GeneratedContent
from src.flow.prompts.system.content import CONTENT_SYSTEM_PROMPT
from langchain.agents.structured_output import ToolStrategy
from src.flow.model.llm_manager import load_content_model
from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware

async def create_content_agent(
    model: Optional[Any] = None,
    tools: Optional[Sequence[BaseTool | Callable | dict[str, Any]]] = None,
    system_prompt: str = CONTENT_SYSTEM_PROMPT,
    rext_middleware: Sequence[AgentMiddleware] = (),
    debug: bool = False,
    name: Optional[str] = "content_agent",
    cache: Optional[BaseCache] = None,
    agent_store=None,
    response_format = ToolStrategy(GeneratedContent),
    user_id: Optional[UUID] = None,
    workspace_id: Optional[UUID] = None,
    outline: Optional[dict] = None,
) -> CompiledStateGraph:
    """
    Create a content agent with parent/child tool routing AND dynamic integration tools.
    REMOVED: No db/user_id/agent_id/workspace_id/active_integrations params - all handled internally.
    """

    # Assemble Base Tools (include ALL known tools so executor can run them)
    if tools is None:
        tools = get_tools()
    else:
        tools_list = list(tools)
        tools = tools_list

    if model is None:
        model = load_content_model()

    # Middleware Stack
    middleware_stack = [
      PersonaInjectionMiddleware(
        workspace_id=workspace_id,
        user_id=user_id,
        outline=outline,
      )
    ]

    if rext_middleware:
      middleware_stack.extend(rext_middleware)

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware_stack,
        debug=debug,
        name=name,
        cache=cache,
        store=agent_store,
        response_format=response_format,
    ).with_config({"recursion_limit": 100})


if __name__ == "__main__":
    import asyncio

    async def main():
        # Initialize the agent
        agent = await create_content_agent(debug=True)

        input_data = {
            "messages": [
                {
                    "role": "user",
                    "content": """
                    {
  "title": "AI in SEO 2026: How to Utilize Artificial Intelligence for Better Rankings",
  "slug_suggestion": "ai-in-seo-2026",
  "brief": "Provide a practical, data-aware guide on how marketers and businesses can use AI to improve SEO performance in 2026, covering keyword research, content optimization, technical SEO, and analytics.",
  
  "focus_keyphrase": "AI in SEO",
  "keywords_to_include": [
    "AI SEO tools",
    "AI content optimization",
    "SEO automation",
    "AI keyword research",
    "future of SEO"
  ],

  "sections": [
    {
      "heading": "Why AI in SEO Matters in 2026",
      "heading_level": "H2",
      "description": "Explain the growing role of AI in search engines and why it is essential for modern SEO strategies.",
      "key_points": [
        "Search engines increasingly rely on machine learning models",
        "AI influences ranking, personalization, and SERP features",
        "Shift from keyword matching to intent understanding"
      ],
      "questions_to_answer": [
        "Why is AI important for SEO?",
        "How is Google using AI in search?"
      ],
      "snippet_target": true,
      "search_intent": "informational",
      "suggested_word_count": 200,
      "include_keyphrase_in_heading": true,
      "facts": [
        {
          "text": "Google uses machine learning systems like RankBrain and neural matching to better understand search queries.",
          "source_url": "https://developers.google.com/search/docs/fundamentals/how-search-works"
        }
      ]
    },
    {
      "heading": "AI-Powered Keyword Research and Search Intent Analysis",
      "heading_level": "H2",
      "description": "Show how AI tools help discover keyword clusters and understand user intent.",
      "key_points": [
        "AI tools group keywords by semantic relevance",
        "Intent-based SEO is more effective than single keyword targeting",
        "AI can uncover long-tail opportunities faster"
      ],
      "questions_to_answer": [
        "How to use AI for keyword research?",
        "What is search intent in SEO?"
      ],
      "snippet_target": false,
      "search_intent": "informational",
      "suggested_word_count": 250,
      "include_keyphrase_in_heading": false,
      "facts": [
        {
          "text": "Modern SEO tools like Ahrefs and Semrush use machine learning to cluster keywords based on SERP similarity.",
          "source_url": "https://ahrefs.com/blog/keyword-clustering/"
        }
      ]
    },
    {
      "heading": "How to Use AI for Content Creation and Optimization",
      "heading_level": "H2",
      "description": "Explain how AI assists in drafting, optimizing, and scaling content while maintaining quality.",
      "key_points": [
        "AI speeds up content drafting and ideation",
        "Human editing is required for accuracy and tone",
        "AI helps optimize headings, meta tags, and readability"
      ],
      "questions_to_answer": [
        "Can AI write SEO content?",
        "Is AI-generated content good for SEO?"
      ],
      "snippet_target": true,
      "search_intent": "informational",
      "suggested_word_count": 250,
      "include_keyphrase_in_heading": false,
      "facts": [
        {
          "text": "Google states that AI-generated content is acceptable if it is helpful, reliable, and created for users.",
          "source_url": "https://developers.google.com/search/blog/2023/02/google-search-and-ai-content"
        }
      ]
    },
    {
      "heading": "Using AI for Technical SEO and Site Performance",
      "heading_level": "H2",
      "description": "Discuss how AI can automate technical audits and improve site performance.",
      "key_points": [
        "AI tools can identify crawl issues and duplicate content",
        "Automation improves efficiency in large websites",
        "AI helps monitor Core Web Vitals and performance issues"
      ],
      "questions_to_answer": [
        "How does AI help technical SEO?",
        "Can AI fix SEO issues automatically?"
      ],
      "snippet_target": false,
      "search_intent": "informational",
      "suggested_word_count": 200,
      "include_keyphrase_in_heading": false,
      "facts": [
        {
          "text": "Core Web Vitals are a confirmed Google ranking factor related to page experience.",
          "source_url": "https://developers.google.com/search/docs/appearance/page-experience"
        }
      ]
    },
    {
      "heading": "AI in Link Building and Outreach Strategies",
      "heading_level": "H2",
      "description": "Explain how AI helps identify backlink opportunities and automate outreach.",
      "key_points": [
        "AI can analyze competitor backlinks",
        "Personalized outreach emails can be generated with AI",
        "Content quality still drives natural backlinks"
      ],
      "questions_to_answer": [
        "Can AI help with link building?",
        "What is the best way to get backlinks in 2026?"
      ],
      "snippet_target": false,
      "search_intent": "informational",
      "suggested_word_count": 200,
      "include_keyphrase_in_heading": false,
      "facts": []
    },
    {
      "heading": "Measuring SEO Performance with AI Analytics",
      "heading_level": "H2",
      "description": "Cover how AI improves SEO tracking, forecasting, and reporting.",
      "key_points": [
        "AI can analyze large SEO datasets quickly",
        "Predictive analytics helps forecast trends",
        "Automation improves reporting efficiency"
      ],
      "questions_to_answer": [
        "How to track SEO performance with AI?",
        "What metrics matter in AI SEO?"
      ],
      "snippet_target": false,
      "search_intent": "informational",
      "suggested_word_count": 200,
      "include_keyphrase_in_heading": false,
      "facts": []
    },
    {
      "heading": "Future of AI in SEO: Trends to Watch",
      "heading_level": "H2",
      "description": "Highlight upcoming trends like generative search and multimodal SEO.",
      "key_points": [
        "Generative search experiences are evolving",
        "Multimodal search includes text, images, and video",
        "SEO will focus more on context and user experience"
      ],
      "questions_to_answer": [
        "What is the future of SEO with AI?",
        "Will AI replace SEO?"
      ],
      "snippet_target": true,
      "search_intent": "informational",
      "suggested_word_count": 200,
      "include_keyphrase_in_heading": false,
      "facts": [
        {
          "text": "Google is integrating generative AI features into search results through its Search Generative Experience (SGE).",
          "source_url": "https://blog.google/products/search/generative-ai-search/"
        }
      ]
    }
  ],

  "faqs": [
    "How is AI changing SEO in 2026?",
    "Is AI-generated content safe for Google rankings?",
    "What are the best AI tools for SEO?",
    "Can beginners use AI for SEO?"
  ],

  "key_facts": [
    {
      "text": "Google emphasizes helpful, people-first content regardless of whether it is AI-generated or human-written.",
      "source_url": "https://developers.google.com/search/docs/fundamentals/creating-helpful-content"
    }
  ],

  "image_suggestions": [
    {
      "description": "Diagram showing AI SEO workflow including keyword research, content creation, technical SEO, and analytics",
      "alt_text_template": "AI in SEO workflow diagram showing keyword research, content optimization, and analytics process",
      "section": "introduction"
    },
    {
      "description": "Screenshot-style illustration of keyword clustering using an SEO tool",
      "alt_text_template": "AI keyword clustering example for SEO showing grouped search intent keywords",
      "section": "AI-Powered Keyword Research and Search Intent Analysis"
    }
  ],

  "link_suggestions": [
    {
      "anchor_text": "AI SEO tools guide",
      "link_type": "internal",
      "context": "Link to a detailed article about AI SEO tools and comparisons",
      "section": "AI-Powered Keyword Research and Search Intent Analysis"
    },
    {
      "anchor_text": "Google Search documentation",
      "link_type": "outbound",
      "context": "Reference official Google documentation on how search works",
      "section": "Why AI in SEO Matters in 2026"
    }
  ],

  "schema_type": "Article",

  "target_audience": [
    "SEO professionals",
    "digital marketers",
    "content creators",
    "business owners"
  ],

  "tone": "Authoritative",

  "target_word_count": 1800
}

Now Based on the outline generate the content
                    """
                }
            ]
        }

        print("--- Agent Execution with Streaming & Tool Calling ---")
        
        # # We use astream_events (v2) to capture both tokens and tool execution details
        # async for event in agent.astream_events(input_data, version="v2"):
        #     kind = event["event"]
        #     print("Event: ", event, "\n")
        #     print("Event Kind: ", kind, "\n")
            
        #     # Show streaming tokens from the LLM
        #     if kind == "on_chat_model_stream":
        #         content = event["data"]["chunk"].content
        #         if content:
        #             print(content, end="", flush=True)
            
        #     # Show when a tool is being called
        #     elif kind == "on_tool_start":
        #         print(f"\n\n[Tool Call] >>> Calling tool: {event['name']}")
        #         print(f"[Tool Input] {event['data'].get('input')}\n")
            
        #     # Show when a tool finishes execution
        #     elif kind == "on_tool_end":
        #         print(f"\n[Tool Result] <<< Tool '{event['name']}' execution finished.\n")
            
        #     # Show when the agent finishes
        #     elif kind == "on_agent_end":
        #         print(f"\n[Agent Result] <<< Agent execution finished.\n")
        #         # print(f"[Final Output] {event['data'].get('output')}\n")
        #          # Only process the final structured GeneratedContent response
        #         structured_response = event['data'].get('output')
        #         if isinstance(structured_response, GeneratedContent):
        #             import json
        #             response_dict = structured_response.model_dump()
        #             response_json = json.dumps(response_dict, indent=2, ensure_ascii=False)
        #             print(f"[Structured Response JSON]\n{response_json}\n")
        #     elif kind == "on_chain_end" and not event.get('parent_ids'):
        #         # Top-level graph end: output is {'messages': [...]}
        #         # The structured JSON is in the last AIMessage's content
        #         import json
        #         output = event['data'].get('output')
        #         if isinstance(output, GeneratedContent):
        #             response_dict = output.model_dump()
        #         elif isinstance(output, dict) and 'messages' in output:
        #             messages = output['messages']
        #             last_msg = messages[-1] if messages else None
        #             content = getattr(last_msg, 'content', '') if last_msg else ''
        #             try:
        #                 response_dict = json.loads(content) if content else None
        #             except (json.JSONDecodeError, TypeError):
        #                 response_dict = None
        #         else:
        #             response_dict = None

        #         if response_dict:
        #             response_json = json.dumps(response_dict, indent=2, ensure_ascii=False)
        #             print(f"\n[Structured Response JSON]\n{response_json}\n")

        final_output = await agent.ainvoke(input_data)
        structured_output = final_output.get("structured_response")
        if isinstance(structured_output, GeneratedContent):
            content_dict = structured_output.model_dump()
        else:
            # Fallback parse if needed
            content_dict = json.loads(final_output["messages"][-1].content)

        print(f"Content generated: {content_dict.get('title', '')}")
                
        print("\n\n--- Execution Complete ---")

    asyncio.run(main())
 