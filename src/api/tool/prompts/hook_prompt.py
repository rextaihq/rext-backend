from langchain_core.prompts import PromptTemplate

hook_prompt = PromptTemplate.from_template(
    """You are an expert content strategist and copywriter. Your task is to generate {number_of_variations} catchy, attention-grabbing hooks for the following topic.

Topic Description: {topic_description}
Goal of Content: {goal_of_content}

Instructions:
1. Generate exactly {number_of_variations} unique hooks.
2. Each hook should be designed to grab attention immediately.
3. Use different styles (e.g., question, bold statement, curiosity gap, relatable problem).
4. Return the result as a simple list of hooks, one per line, without any numbering or extra text.

Hooks:"""
)
