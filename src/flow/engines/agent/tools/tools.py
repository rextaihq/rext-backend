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

from langchain_core.tools import tool

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
    return [search_tool, generate_image, detect_ai_vocab]

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
    "let’s explore",
    "let’s take a look at",
    "in this article we will",

    # =========================
    # AI INTRO / TRANSITION PHRASES
    # =========================
    "it is important to note",
    "it’s important to note",
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
    "It’s important to recognize",

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
    "in today’s world",
    "in modern society",
    "in recent years",
    "over the years",
    "a wide range of",
    "a variety of",
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