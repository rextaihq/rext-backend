from langchain_core.prompts import PromptTemplate

headline_analyzer_prompt = PromptTemplate(
    input_variables=["headline"],
    template="""You are an expert Copywriter and Conversion Rate Optimization (CRO) strategist.

Analyze the following headline for CTR potential, emotional impact, and SEO effectiveness:
"{headline}"

Analyze and provide feedback on:
1. Overall Quality / CTR Score (0 to 100)
2. Sentiment (Positive, Neutral, or Negative)
3. Power / Emotional Words present in the headline
4. Estimated Reading Level (e.g. Easy, Intermediate, Complex)
5. 2-3 actionable improvement suggestions to make the headline more magnetic.

Be objective, constructive, and accurate.
""",
)
