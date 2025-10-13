class LangGraphBaseClient:
    """
    Base client for interacting with LangGraph API.

    Handles client initialization, authentication, and provides a safe
    method to call LangGraph SDK functions with error handling.

    Attributes:
        url (str): Base URL of the LangGraph API.
        api_key (str | None): Optional API key for authentication.
        _client: Cached LangGraph SDK client instance.
    """

    def __init__(self, url: str, api_key: str | None = None):
        """
        Initialize the base client.

        Args:
            url (str): Base URL for the LangGraph API.
            api_key (str | None, optional): API key for authentication. Defaults to None.
        """
        self.url = url
        self.api_key = api_key
        self._client = None

    async def get_client(self):
        """
        Lazily initialize and return the LangGraph SDK client.

        If the client already exists, returns the cached instance.
        If an API key is provided, it sets the Authorization header.

        Returns:
            LangGraphClient: An initialized LangGraph SDK client.
        """
        if self._client is None:
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
