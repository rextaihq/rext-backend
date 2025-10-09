from langsmith import Client
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
load_dotenv()


def get_client():
    client = Client()

    return client


if __name__ == "__main__":
    client = get_client()
    prompt = ChatPromptTemplate([
        ("system", "You are a helpful assistant writing blog posts."),
        ("user", "Write a blog post on {topic} using keywords: {keywords}."),
    ])

    client.push_prompt("blog_post_prompt", object=prompt)