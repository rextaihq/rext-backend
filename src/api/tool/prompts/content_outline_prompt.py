from langchain_core.prompts import PromptTemplate

content_outline_prompt = PromptTemplate(
    input_variables=["topic", "content_type", "outline_depth", "tone"],
    template="""
You are an expert Content Strategist and SEO Specialist. Your task is to generate a well-structured content outline for the topic: "{topic}".

### Context:
- **Content Type:** {content_type}
- **Outline Depth:** {outline_depth}
- **Tone:** {tone}

### Instructions:
1. Create a comprehensive outline with clear headings (H1, H2, H3 level).
2. For each heading, provide relevant key points or subpoints.
3. If outline_depth is "basic", provide 3-5 main headings with 2-3 subpoints each.
4. If outline_depth is "detailed", provide 5-8 main headings with 3-5 subpoints each.
5. Ensure the outline is logical, flows naturally, and covers all important aspects of the topic.
6. Use the specified tone throughout the outline.
7. Make subpoints specific, actionable, and relevant to the heading.

### Output Format:
Return ONLY structured data matching this exact JSON schema. Do not include any extra text, explanations, or markdown formatting.

The response must follow this structure:
{{
  "outline": [
    {{
      "heading": "Main Heading 1",
      "subpoints": ["Key point 1", "Key point 2", "Key point 3"]
    }},
    {{
      "heading": "Main Heading 2",
      "subpoints": ["Key point 1", "Key point 2"]
    }}
  ]
}}

CRITICAL: Return ONLY valid JSON. No markdown, no code blocks, no extra text.
"""
)
