from langchain_core.prompts import PromptTemplate

seo_blog_title_prompt = PromptTemplate.from_template(
    """You are an SEO content strategist.

Generate {number_of_topics} SEO-friendly blog titles based on the keyword:
"{keyword}"

Rules:
- Each title must be between {min_words} and {max_words} words
- Titles must be concise, clear, and engaging
- Use natural, human-friendly language
- Avoid clickbait symbols, emojis, or hashtags
- Capitalize properly like a real blog headline
- Focus on modern tech, AI, and real-world use cases
- Do NOT add explanations, bullet points, or numbering
- Return only the blog titles, one per line

Style reference:
"5 free AI tools tech workers love right now."
"Fix AI bias in your code step by step."
"ChatGPT vs. Grok: best for daily coding."

Blog Titles:"""
)
