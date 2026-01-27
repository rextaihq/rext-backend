from langchain_core.prompts import PromptTemplate


generate_conclusion_prompt_template = PromptTemplate(
        input_variables=["content", "tone", "length"],
        template="""
        You are an expert content writer.

Write a strong, well-structured conclusion for the following content.

Content:
{content}

Guidelines:
- Tone: {tone}
- Length: {length}
- Do NOT repeat sentences from the content
- Summarize key takeaways clearly
- Add a natural closing thought or call-to-action if appropriate
- Keep it human, clear, and engaging
- No headings
- No bullet points
- No explanations

Return ONLY the conclusion text.

""")