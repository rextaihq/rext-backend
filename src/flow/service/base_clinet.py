from langgraph.pregel.remote import RemoteGraph
from src.utils.logger import logger
import os

class LangGraphRemoteGraph:
    """
    Base client for interacting with LangGraph API.

    Handles client initialization, authentication, and provides a safe
    method to call LangGraph SDK functions with error handling.

    Attributes:
        url (str): Base URL of the LangGraph API.
        api_key (str | None): Optional API key for authentication.
        _client: Cached LangGraph SDK client instance.
    """

    def __init__(
        self, 
        assistant_id: str, 
        name: str = "WREXT", 
        api_key: str | None = None,
        url: str = os.getenv("LANGSMITH_DEV_URL")
    ):
        """
        Initialize the base client.

        Args:
            url (str): Base URL for the LangGraph API.
            api_key (str | None, optional): API key for authentication. Defaults to None.
        """
        self.url = url
        # Ensure URL includes protocol scheme; prepend https:// if missing
        if not (self.url.startswith('http://') or self.url.startswith('https://')):
            self.url = f"https://{self.url}"
        self.api_key = api_key
        self.assistant_id = assistant_id
        self.name:str=name
        # ✅ Fix: Initialize lazy attributes
        self._client = None
        self.remote_graph = None

    async def create_assistant_if_needed(self):
        """Create an assistant if assistant_id is None."""
        if self.assistant_id is None:
            logger.info("No assistant_id found. Creating a new assistant...")
            client = await self.get_client()
            result = await client.assistants.create(
                graph_id="agent",
                config={},
                metadata={},
                name=self.name
            )
            self.assistant_id = result["assistant_id"]
            logger.info(f"Assistant created with ID: {self.assistant_id}")

    async def get_remote_graph(self):
        """
        Lazily initialize and return the LangGraph SDK client.

        If the client already exists, returns the cached instance.
        If an API key is provided, it sets the Authorization header.

        Returns:
            LangGraphClient: An initialized LangGraph SDK client.
        """
        logger.info("inside get remote graph of base client") 
        logger.info(f"URL: {self.url}, API Key: {self.api_key}, Name: {self.name}")  
        await self.create_assistant_if_needed()
        self.remote_graph= RemoteGraph(
                self.assistant_id,
                url=self.url,
                api_key=self.api_key,
                name=self.name
                )
        return self.remote_graph

    async def get_client(self):
        """
        Lazily initialize and return the LangGraph SDK client.

        If the client already exists, returns the cached instance.
        If an API key is provided, it sets the Authorization header.

        Returns:
            LangGraphClient: An initialized LangGraph SDK client.
        """
        if self._client is None:
            logger.info(f"Initializing LangGraph client...{self.url}")
            from langgraph_sdk import get_client
            client = get_client(url=self.url)
            if self.api_key:
                try:
                    client.http.client.headers["Authorization"] = f"Bearer {self.api_key}"
                except Exception:
                    pass
            self._client = client
        return self._client

    async def safe_call(self, coro, context: str = ""):
        """
        Safely execute a coroutine and handle exceptions.

        Logs any exceptions with the provided context and re-raises them.

        Args:
            coro (Coroutine): The coroutine to execute.
            context (str, optional): Contextual message for logging errors. Defaults to "".

        Returns:
            Any: Result of the awaited coroutine.

        Raises:
            Exception: Re-raises any exception encountered during the coroutine execution.
        """
        try:
            return await coro
        except Exception as e:
            import logging
            logging.error(f"LangGraph error in {context}: {e}")
            raise
