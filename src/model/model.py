from langchain.chat_models import init_chat_model
from src.states.State import Evaluation

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
