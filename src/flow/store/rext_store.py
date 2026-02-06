import uuid
from typing import Optional, Any

from langgraph.store.postgres import AsyncPostgresStore
from langchain_openai import OpenAIEmbeddings
from src.api.config import settings


class RextStore:
    """
    Service class for managing persistent vector storage using LangGraph's AsyncPostgresStore.
    Handles knowledge storage with namespacing based on user_id and workspace_id.
    """
    
    def __init__(self):
        self._store: Optional[AsyncPostgresStore] = None
        self._db_uri = self._get_db_uri()
    
    @staticmethod
    def _get_db_uri() -> str:
        """
        Get and convert the database URI to psycopg-compatible format.
        SQLAlchemy uses 'postgresql+asyncpg://' but psycopg expects 'postgresql://'.
        """
        uri = settings.POSTGRES_URI_CUSTOM
        
        # Convert SQLAlchemy async format to standard PostgreSQL format
        if uri.startswith("postgresql+asyncpg://"):
            uri = uri.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif uri.startswith("postgresql+psycopg://"):
            uri = uri.replace("postgresql+psycopg://", "postgresql://", 1)
        
        return uri
    
    @staticmethod
    def _get_embeddings() -> OpenAIEmbeddings:
        """Get OpenAI embeddings instance (dims=1536)."""
        return OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=settings.OPENAI_API_KEY
        )
    
    async def _get_embed_func(self):
        """Create the embedding function for the store."""
        embeddings = self._get_embeddings()
        
        async def embed_texts(texts: list[str]) -> list[list[float]]:
            return await embeddings.aembed_documents(texts)
        
        return embed_texts
    
    async def _create_store(self) -> AsyncPostgresStore:
        """Factory to create a configured store instance."""
        embed_func = await self._get_embed_func()
        
        return AsyncPostgresStore.from_conn_string(
            self._db_uri,
            index={
                "dims": 1536,
                "embed": embed_func,
                "fields": ["text"]  # Fields to vectorize in the JSON data
            }
        )
    
    # =========================================================================
    # Namespace Helpers
    # =========================================================================
    
    @staticmethod
    def build_namespace(
        user_id: str | uuid.UUID,
        workspace_id: str | uuid.UUID
    ) -> tuple[str, ...]:
        """
        Build a namespace tuple for the store based on user_id and workspace_id.
        
        Format: ("knowledge", user_id, workspace_id)
        
        Returns:
            tuple: The namespace tuple for the store
        """
        return ("knowledge", str(user_id), str(workspace_id))

    # =========================================================================
    # CRUD Operations
    # =========================================================================
    
    async def save(
        self,
        namespace: tuple[str, ...],
        content: str,
        metadata: dict | None = None
    ) -> str:
        """
        Save content to a specific namespace.
        
        Args:
            namespace: The namespace tuple (e.g., ("knowledge", "user_id", "workspace_id"))
            content: The text content to store
            metadata: Optional metadata dict
            
        Returns:
            str: The generated item ID
        """
        async with await self._create_store() as store:
            item_id = str(uuid.uuid4())
            
            await store.aput(
                namespace,
                item_id,
                {
                    "text": content,
                    "metadata": metadata or {"source": "manual"}
                }
            )
            print(f"Stored item {item_id} in namespace {namespace}")
            return item_id
    
    async def save_knowledge(
        self,
        user_id: str | uuid.UUID,
        workspace_id: str | uuid.UUID,
        content: str,
        metadata: dict | None = None,
        source: str = "web"
    ) -> str:
        """
        Save knowledge content with automatic namespace building.
        
        Args:
            user_id: The user ID
            workspace_id: The workspace ID
            content: The text content to store
            metadata: Optional additional metadata
            source: Source type (e.g., "web", "file", "youtube")
        
        Returns:
            str: The generated item ID
        """
        namespace = self.build_namespace(user_id, workspace_id)
        
        # Build metadata
        full_metadata = {
            "source": source,
            "user_id": str(user_id),
            "workspace_id": str(workspace_id),
        }
        
        if metadata:
            full_metadata.update(metadata)
        
        async with await self._create_store() as store:
            item_id = str(uuid.uuid4())
            
            await store.aput(
                namespace,
                item_id,
                {
                    "text": content,
                    "metadata": full_metadata
                }
            )
            print(f"Stored knowledge item {item_id} in namespace {namespace}")
            return item_id
    
    async def save_knowledge_batch(
        self,
        user_id: str | uuid.UUID,
        workspace_id: str | uuid.UUID,
        contents: list[dict],
        source: str = "web"
    ) -> list[str]:
        """
        Save multiple knowledge items in batch.
        
        Args:
            user_id: The user ID
            workspace_id: The workspace ID
            contents: List of dicts with 'text' and optional 'metadata' keys
            source: Source type (e.g., "web", "file", "youtube")
        
        Returns:
            list[str]: List of generated item IDs
        """
        namespace = self.build_namespace(user_id, workspace_id)
        item_ids = []
        
        # Build base metadata
        base_metadata = {
            "source": source,
            "user_id": str(user_id),
            "workspace_id": str(workspace_id),
        }
        
        async with await self._create_store() as store:
            for item in contents:
                item_id = str(uuid.uuid4())
                
                # Merge base metadata with item-specific metadata
                full_metadata = {**base_metadata}
                if item.get("metadata"):
                    full_metadata.update(item["metadata"])
                
                await store.aput(
                    namespace,
                    item_id,
                    {
                        "text": item["text"],
                        "metadata": full_metadata
                    }
                )
                item_ids.append(item_id)
            
            print(f"Stored {len(item_ids)} knowledge items in namespace {namespace}")
            return item_ids
    
    async def get(
        self,
        namespace: tuple[str, ...],
        key: str
    ) -> Optional[Any]:
        """
        Get a specific item from the store by key.
        
        Args:
            namespace: The namespace tuple
            key: The item ID/key
            
        Returns:
            The stored item or None if not found
        """
        async with await self._create_store() as store:
            result = await store.aget(namespace, key)
            return result
    
    async def get_knowledge(
        self,
        user_id: str | uuid.UUID,
        workspace_id: str | uuid.UUID,
        key: str
    ) -> Optional[Any]:
        """
        Get a specific knowledge item.
        
        Args:
            user_id: The user ID
            workspace_id: The workspace ID
            key: The item ID/key
            
        Returns:
            The stored item or None if not found
        """
        namespace = self.build_namespace(user_id, workspace_id)
        return await self.get(namespace, key)
    
    async def delete(
        self,
        namespace: tuple[str, ...],
        key: str
    ) -> None:
        """
        Delete a specific item from the store.
        
        Args:
            namespace: The namespace tuple
            key: The item ID/key to delete
        """
        async with await self._create_store() as store:
            await store.adelete(namespace, key)
            print(f"Deleted item {key} from namespace {namespace}")
    
    async def delete_knowledge(
        self,
        user_id: str | uuid.UUID,
        workspace_id: str | uuid.UUID,
        key: str
    ) -> None:
        """
        Delete a specific knowledge item.
        
        Args:
            user_id: The user ID
            workspace_id: The workspace ID
            key: The item ID/key to delete
        """
        namespace = self.build_namespace(user_id, workspace_id)
        await self.delete(namespace, key)
    
    async def search(
        self,
        namespace: tuple[str, ...],
        query: str,
        filter: dict | None = None,
        limit: int = 10
    ) -> list[Any]:
        """
        Search for items in a namespace using semantic search.
        
        Args:
            namespace: The namespace tuple
            query: The search query
            filter: Optional dictionary to filter by metadata
            limit: Maximum number of results to return
            
        Returns:
            List of matching items
        """
        async with await self._create_store() as store:
            results = await store.asearch(namespace, query=query, filter=filter, limit=limit)
            return results
    
    async def search_knowledge(
        self,
        user_id: str | uuid.UUID,
        workspace_id: str | uuid.UUID,
        query: str,
        filter: dict | None = None,
        limit: int = 10
    ) -> list[Any]:
        """
        Search for knowledge items using semantic search.
        
        Args:
            user_id: The user ID
            workspace_id: The workspace ID
            query: The search query
            filter: Optional dictionary to filter by metadata
            limit: Maximum number of results to return
            
        Returns:
            List of matching items
        """
        namespace = self.build_namespace(user_id, workspace_id)
        return await self.search(namespace, query, filter, limit)
    
    async def list_items(
        self,
        namespace: tuple[str, ...],
        limit: int = 100,
        offset: int = 0
    ) -> list[Any]:
        """
        List all items in a namespace.
        
        Args:
            namespace: The namespace tuple
            limit: Maximum number of items to return
            offset: Number of items to skip
            
        Returns:
            List of items in the namespace
        """
        async with await self._create_store() as store:
            results = await store.asearch(namespace, limit=limit, offset=offset)
            return results
    
    async def list_knowledge(
        self,
        user_id: str | uuid.UUID,
        workspace_id: str | uuid.UUID,
        limit: int = 100,
        offset: int = 0
    ) -> list[Any]:
        """
        List all knowledge items for a user/workspace.
        
        Args:
            user_id: The user ID
            workspace_id: The workspace ID
            limit: Maximum number of items to return
            offset: Number of items to skip
            
        Returns:
            List of knowledge items
        """
        namespace = self.build_namespace(user_id, workspace_id)
        return await self.list_items(namespace, limit, offset)
    
    async def setup(self) -> None:
        """Initialize the store (creates tables if needed)."""
        async with await self._create_store() as store:
            await store.setup()
            print("✅ Store setup complete!")

if __name__ == "__main__":
    import asyncio
    
    async def main():
        store = RextStore()
        
        # Dummy data for testing
        test_user_id = "test-user-123"
        test_workspace_id = "test-workspace-456"
        
        print(f"--- Setting up store ---")
        await store.setup()
        
        print(f"\n--- Storing dummy data for user: {test_user_id}, workspace: {test_workspace_id} ---")
        
        dummy_content = [
            {"text": "The Capital of France is Paris.", "metadata": {"topic": "geography"}},
            {"text": "Python is a versatile programming language.", "metadata": {"topic": "programming"}},
            {"text": "The Earth orbits the Sun once every 365.25 days.", "metadata": {"topic": "science"}}
        ]
        
        item_ids = await store.save_knowledge_batch(
            user_id=test_user_id,
            workspace_id=test_workspace_id,
            contents=dummy_content,
            source="dummy_test"
        )
        
        print(f"\n--- Listing stored items ---")
        items = await store.list_knowledge(test_user_id, test_workspace_id)
        for item in items:
            print(f"ID: {item.key}, Content: {item.value['text']}, Metadata: {item.value['metadata']}")
            
        print(f"\n--- Searching for 'Paris' ---")
        results = await store.search_knowledge(test_user_id, test_workspace_id, query="What is the capital of France?")
        for res in results:
            print(f"Found: {res.value['text']} (Score: {res.score})")

    asyncio.run(main())