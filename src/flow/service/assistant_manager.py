class AssistantManager:
    """
    Manager for handling LangGraph assistants.

    Provides methods to create assistants, fetch assistant details, 
    and retrieve assistant schemas. Assumes `get_client()` is implemented 
    in the parent class or mixed in to provide a LangGraphClient instance.

    Methods:
        create_assistant: Create a new assistant (graph flow) in LangGraph.
        get_assistant: Retrieve details of an existing assistant by ID.
        get_schemas: Retrieve the input/output schemas of an assistant.
    """
    async def create_assistant(self, graph_id, config=None, metadata=None, name=None):
        """
        Create a new assistant in LangGraph.

        Args:
            graph_id (str): The ID of the graph to associate with the assistant.
            config (dict, optional): Assistant configuration parameters.
            metadata (dict, optional): Metadata to attach to the assistant.
            name (str, optional): Friendly name for the assistant.

        Returns:
            dict: The created assistant object returned by LangGraph.
        """
        client = await self.get_client()
        return await client.assistants.create(
            graph_id=graph_id, config=config or {}, metadata=metadata or {}, name=name
        )

    async def get_assistant(self, assistant_id):
        """
        Retrieve an existing assistant's details.

        Args:
            assistant_id (str): The unique ID of the assistant.

        Returns:
            dict: Assistant details returned by LangGraph.
        """
        client = await self.get_client()
        return await client.assistants.get(assistant_id)

    async def get_schemas(self, assistant_id):
        """
        Retrieve the input/output schemas of an assistant.

        Args:
            assistant_id (str): The unique ID of the assistant.

        Returns:
            dict: Schemas of the assistant, including input and output definitions.
        """
        client = await self.get_client()
        return await client.assistants.get_schemas(assistant_id)
