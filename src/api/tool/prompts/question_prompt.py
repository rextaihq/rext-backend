from langchain_core.prompts import PromptTemplate

question_prompt = PromptTemplate(
    input_variables=["text"],
    template="""
You are an expert Content Strategist. Based on the following text, generate 5-10 engaging, relevant, and thought-provoking questions that readers might have or that could be used for a FAQ section.

### Text:
{text}

### Output Instruction:
Return ONLY the questions, one per line, without numbers or bullets.
""",
)
