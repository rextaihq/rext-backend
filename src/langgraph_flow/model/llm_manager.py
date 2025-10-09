from langchain.chat_models import init_chat_model
from src.states.schemas import RewriterTitle, QueryDecomposer
from sentence_transformers import SentenceTransformer
from src.states.schemas import BasicTopicGenerationList
from langsmith import trace, traceable, Client
from dotenv import load_dotenv
import os

load_dotenv()
def load_model():
    """
    Initializes and returns a chat model using LangChain's `init_chat_model`.

    This function loads the `gpt-4o-mini` model from the OpenAI provider.

    Returns:
        BaseChatModel: An instance of the initialized chat model.
    """
    model = init_chat_model("gpt-4o-mini", model_provider="openai",api_key=os.getenv("OPENAI_API_KEY"))
    return model

def topic_generation_model():
    """
    Initializes a chat model and enhances it to return structured output
    based on the provided Pydantic schema (`BasicTopicGeneration`).

    This is useful for tasks where the model's output must follow a specific
    format, such as form-based responses, evaluations, or other structured data.

    Returns:
        BaseStructuredChatModel: A chat model that returns outputs conforming to the `BasicTopicGeneration` schema.
    """
    model = load_model()
    model_with_parser = model.with_structured_output(BasicTopicGenerationList)
    return model_with_parser


def search_model():
    """
    Initializes and returns a chat model using LangChain's `init_chat_model`.

    This function loads the `gpt-4o-mini` model from the OpenAI provider.

    Returns:
        BaseChatModel: An instance of the initialized chat model.
    """
    model = init_chat_model("gpt-4o-mini", model_provider="openai")
    return model


def load_embedder():
        """
        Loads and returns a SentenceTransformer embedder using the 'all-MiniLM-L6-v2' model on CPU.

        Returns:
            SentenceTransformer: An instance of the SentenceTransformer model for generating embeddings.
        """
        embedder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',device="cpu")
        return embedder


def title_refine_model():
    llm = load_model()
    return llm.with_structured_output(RewriterTitle)


def query_decomposer_model():
    llm  = load_model()
    return llm.with_structured_output(QueryDecomposer)

