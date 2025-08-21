from langchain.chat_models import init_chat_model
from src.states.State import Evaluation,RewriterQuery,QueryDecomposer
from sentence_transformers import SentenceTransformer
import torch

def LoadModel():
    """
    Initializes and returns a chat model using LangChain's `init_chat_model`.

    This function loads the `gpt-4o-mini` model from the OpenAI provider.

    Returns:
        BaseChatModel: An instance of the initialized chat model.
    """
    model = init_chat_model("gpt-4o-mini", model_provider="openai")
    return model


def StructuredModel():
    """
    Initializes a chat model and enhances it to return structured output 
    based on the provided Pydantic schema (`Evaluation`).

    This is useful for tasks where the model's output must follow a specific 
    format, such as form-based responses, evaluations, or other structured data.

    Returns:
        BaseStructuredChatModel: A chat model that returns outputs conforming to the `Evaluation` schema.
    """
    model = LoadModel()
    model_with_parser = model.with_structured_output(Evaluation)
    return model_with_parser


def searchModel():
    """
    Initializes and returns a chat model using LangChain's `init_chat_model`.

    This function loads the `gpt-4o-mini` model from the OpenAI provider.

    Returns:
        BaseChatModel: An instance of the initialized chat model.
    """
    model = init_chat_model("gpt-4o-mini", model_provider="openai")
    return model


def load_embedder():
    if torch.cuda.is_available():
        embedder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',device="cpu")
        return embedder
    else:
        embedder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',device="cpu")
        return embedder


def title_refine_model():
    llm = LoadModel()
    return llm.with_structured_output(RewriterQuery)


def query_decomposer_model():
    llm  = LoadModel()
    return llm.with_structured_output(QueryDecomposer)