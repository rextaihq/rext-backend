from langchain_core.prompts import PromptTemplate

meta_prompt = PromptTemplate(
    input_variables=["page_title", "keywords"],
    template="""
You are an expert SEO copywriter. Create a compelling meta description for a webpage that will improve click-through rates from search results.

Page Title: {page_title}
Target Keywords: {keywords}

Requirements:
- Length: Between 120-160 characters (aim for 140-150)
- Include the primary keyword naturally
- Write compelling, benefit-focused copy that encourages clicks
- Make it unique and specific to this page
- Include a call-to-action when appropriate
- Focus on value proposition and urgency/benefits

Generate only the meta description text, no additional explanations or quotes.
""",
)
