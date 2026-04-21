from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from dotenv import load_dotenv
from openai import OpenAI
import json
import os

load_dotenv()

@tool
def search_tool(query: str) -> str:
    """Perform a web search using Tavily and return top 5 results with snippets.

    Use this tool for factual questions, current events, research, or up-to-date web info.
    Returns structured results with title, URL, and snippet for citation.

    Args:
        query: Search query (e.g., "best laptops 2024 review")
    """
    search = TavilySearchResults(
        max_results=5,
        search_depth="advanced",
        api_key=os.getenv("TAVILY_API_KEY"),
    )
    results = search.run(query)
    return json.dumps(results, indent=2)


@tool
def generate_image(prompt: str, model: str = "dall-e-3", size: str = "1024x1024"):
    """
    Generates an image using OpenAI's DALL-E model and returns the URL.
    
    Args:
        prompt (str): The text description of the image.
        model (str): The model to use (default "dall-e-3").
        size (str): Image resolution (1024x1024, 1024x1792, or 1792x1024).

    Returns:
        str: The URL of the generated image.
    """
    # Create the OpenAI client
    # Assumes OPENAI_API_KEY is set in your environment variables
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size,
            quality="standard",  # or "hd"
        )
        
        # Extract the URL from the response
        image_url = response.data[0].url
        return image_url

    except Exception as e:
        print(f"Error generating image: {e}")
        return None

@tool
def AI_SIGNAL_STRENGth() -> str:
    """Detect Common AI signals using full production list."""
    return AI_SIGNALS

@tool
def detect_ai_vocab(text: str) -> str:
    """Detect AI vocabulary using full production list."""
    found = set()

    lower = text.lower()

    for phrase in AI_VOCABULARY:
        if phrase in lower:
            found.add(phrase)

    return (
        "No AI vocabulary detected."
        if not found
        else "Detected AI phrases: " + ", ".join(sorted(found))
    )

def get_tools():
    return [search_tool, generate_image, detect_ai_vocab, AI_SIGNAL_STRENGth]

AI_VOCABULARY = {

    # =========================
    # AI ARTICLE / STRUCTURE STARTERS
    # =========================
    "this article explores",
    "this article examines",
    "this article discusses",
    "this section explores",
    "this section discusses",
    "this guide explores",
    "this guide will cover",
    "we will explore",
    "we will examine",
    "we will discuss",
    "let's explore",
    "let's take a look at",
    "in this article we will",

    # =========================
    # AI INTRO / TRANSITION PHRASES
    # =========================
    "it is important to note",
    "it's important to note",
    "it is worth noting",
    "as mentioned earlier",
    "as previously mentioned",
    "moving forward",
    "with that said",
    "that being said",
    "in this context",
    "in this regard",

    # =========================
    # AI CONCLUSION / SUMMARY PHRASES
    # =========================
    "in conclusion",
    "to conclude",
    "in summary",
    "to summarize",
    "overall",
    "ultimately",
    "all things considered",
    "final thoughts",
    "key takeaways",

    # =========================
    # AI TRANSITION WORDS (OVERUSED)
    # =========================
    "furthermore",
    "moreover",
    "however",
    "therefore",
    "thus",
    "consequently",
    "additionally",
    "similarly",
    "in contrast",
    "on the other hand",
    "As we look",
    "In simple terms",
    "It's important to recognize",

    # =========================
    # AI EXPLANATION / FILLER PHRASES
    # =========================
    "this highlights",
    "this demonstrates",
    "this suggests",
    "this indicates",
    "this underscores",
    "it is evident that",
    "it is clear that",
    "it becomes clear that",
    "this shows that",

    # =========================
    # AI VERB PATTERNS (HIGH SIGNAL)
    # =========================
    "delve into",
    "dive into",
    "explore the intricacies",
    "unpack",
    "leverage",
    "utilize",
    "facilitate",
    "enhance",
    "emphasize",
    "underscore",
    "highlight",

    # =========================
    # AI CORPORATE / MARKETING ADJECTIVES
    # =========================
    "robust",
    "scalable",
    "efficient",
    "effective",
    "innovative",
    "cutting-edge",
    "seamless",
    "comprehensive",
    "strategic",
    "optimized",
    "streamlined",
    "dynamic",
    "state-of-the-art",

    # =========================
    # AI GENERIC PHRASES
    # =========================
    "in today's world",
    "in modern society",
    "in recene years",
    "a wide range of",
    "a varit years",
    "over thety of",
    "it is evident that",
    "it is important to understand",
    "this highlights the importance of",

    # =========================
    # AI HEDGING LANGUAGE
    # =========================
    "may indicate",
    "is often considered",
    "tends to",
    "is likely to",
    "generally speaking",
    "can be seen as",
    "could be seen as",
    "might suggest",

    # =========================
    # AI REPETITIVE SENTENCE STARTERS
    # =========================
    "this is because",
    "one of the key reasons",
    "another important factor",
    "a key aspect of",
    "one major advantage",
    "this means that",

    # =========================
    # AI AUTHORITY / CLAIM PHRASES
    # =========================
    "it is crucial to understand",
    "it is essential to consider",
    "it is important to consider",
    "it can be concluded that",
    "the findings suggest that",
    "this indicates that",

    # =========================
    # AI STORYTELLING / GENERIC CONTEXT
    # =========================
    "throughout history",
    "since the dawn of",
    "in the realm of",
    "in the landscape of",
    "in the context of",

    # =========================
    # AI EMAIL / ASSISTANT STYLE
    # =========================
    "i hope this finds you well",
    "as an ai language model",
    "thank you for your question",
    "i apologize for the confusion",

    # =========================
    # AI EMPHASIS / OVERUSE WORDS
    # =========================
    "important",
    "key",
    "significant",
    "crucial",
    "essential",
    "valuable",
    "notable",
    "remarkable",
    "noteworthy",
}


AI_SIGNALS = """

These are AI signals generator, Use this tool to remove all AI pattren from the text.

...

🧠 1. High-Frequency “AI Words” (Core Vocabulary)
These are the most repeated across all articles:
🔹 Formal / Academic Words
Delve (delve into)
Pivotal
Underscore
Realm
Harness
Illuminate
Nuance / nuanced
Intricate
Comprehensive
Significant
Crucial / vital
Enhance
Transform
Optimize
Leverage
Facilitate
Utilize
👉 These words are technically correct but overused, making text feel artificial.


🔹 “Polished but Generic” Words
Robust
Seamless
Dynamic
Innovative
Transformative
Empower
Unlock
Elevate
Foster
Navigate
Explore
Insights / insightful
👉 These create a “perfect but generic” tone (common AI signature).


🧾 2. Common AI Phrases (Very Important)
These are strong detection signals when clustered:
🔹 Exploration / Explanation Phrases
“Delve into…”
“Shed light on…”
“Provide valuable insights…”
“Gain a deeper understanding…”
🔹 Structural / Framing Phrases
“At its core…”
“To put it simply…”
“This underscores the importance of…”
“It is important to note that…”
“It is essential to…”
👉 These are extremely common in AI-generated explanations.


🔹 Transition Phrases (Major AI Signal)
Moreover
Furthermore
Therefore
Consequently
Additionally
That being said
👉 Overuse = robotic flow.


🔹 Conclusion / Summary Phrases
“In conclusion…”
“In summary…”
“Overall…”
👉 Often used in template-style endings.


🏢 3. Corporate / Marketing AI Phrases
“Unlock the power of…”
“Game-changing solution”
“Cutting-edge”
“Take it to the next level”
“Drive synergies”
“Streamline operations”
“Transform your business”
👉 These are highly generic + low specificity → strong AI indicator


⚠️ 4. Hedging / Weak AI Phrases
These reduce confidence and are very common in AI writing:
“Generally speaking…”
“Typically…”
“Tends to…”
“Arguably…”
“To some extent…”
“Broadly speaking…”
👉 AI uses these to avoid making strong claims.


🧩 5. Sentence Patterns That Scream AI
These are more important than individual words:
🔹 Template Sentences
“In today’s fast-paced world…”
“As technology continues to evolve…”
“This article will explore…”
🔹 Over-Structured Logic
“Not only X but also Y”
“It’s not just X—it’s Y”
🔹 Generic Insight Sentences
“This highlights the importance of…”
“This plays a crucial role in…”
“This has significant implications for…”
👉 These are high-probability sentence constructions in AI text.


🔁 6. Metaphorical / “AI Style” Words
Very common across datasets:
Journey
Landscape
Tapestry
Symphony
Era
Ecosystem
Paradigm
👉 AI overuses abstract metaphors instead of concrete language.


🔍 7. Hidden Pattern (Most Important Insight)
Across all sources, the real signal is:
❌ Not individual words
✅ But patterns like:
Too many formal words together
Too many perfect transitions
Too much structure consistency
👉 AI writing = “predictable + polished + repetitive”


✅ Final Consolidated “AI Signal Checklist”
If your text contains many of these together:
Formal words → leverage, enhance, pivotal
Transitions → moreover, furthermore
Phrases → it is important to note
Marketing terms → cutting-edge, unlock
Structure → intro → body → conclusion template
👉 Then it likely feels AI-generated

...


"""