from langchain_core.output_parsers import StrOutputParser
from src.flow.model.llm_manager import load_model
from langchain_core.prompts import PromptTemplate


# =========================
# Conclusion Generator Tool
# =========================

def generate_conclusion(content: str, tone: str = "professional", length: str = "medium") -> str:
    """ Generate a concise conclusion for the given content. """
    
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
    
    llm = load_model()

    chain = generate_conclusion_prompt_template | llm | StrOutputParser()

    response = chain.invoke({
        "content": content,
        "tone": tone,
        "length": length
    })
    conclusion = response.content if hasattr(response, 'content') else str(response)
    return conclusion.strip()

para = "Artificial Intelligence (AI) has rapidly transformed various industries, from healthcare to finance. Its ability to analyze vast amounts of data and generate insights has led to improved decision-making and operational efficiency. As AI continues to evolve, it promises to unlock new opportunities and drive innovation across multiple sectors."
re = generate_conclusion(content=para, tone="inspirational", length="short")

print(re)
