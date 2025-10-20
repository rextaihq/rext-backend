from typing import Any, Dict, Optional, List
from src.utils.logger import logger
from langgraph_sdk import get_client
from langgraph_sdk.client import LangGraphClient

class ThreadManager:
    """
    Manager for LangGraph threads (stateful graph contexts).

    This class provides methods to:
      - Create new threads
      - Get existing threads
      - Update thread metadata or TTL
      - Delete threads
      - Search or list threads
      - Access thread history / state / updates
    """

    async def create_thread(
        self,
        metadata: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        if_exists: Optional[str] = None,
        graph_id: Optional[str] = None,
        supersteps: Optional[List[Dict[str, Any]]] = None,
        ttl: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Create a new thread or reuse an existing one (based on `if_exists` policy).

        Args:
            metadata: Arbitrary metadata to attach to the thread.
            thread_id: Specific ID to assign (or let the server generate).
            if_exists: Behavior if a thread with the same ID already exists (e.g. "raise" or "do_nothing").
            graph_id: (Optional) graph to associate this thread with.
            supersteps: (Optional) initial state supersteps to apply.
            ttl: (Optional) time-to-live or expiry settings.

        Returns:
            A dict representing the created thread from LangGraph.
        """
        client = await self._get_client()
        try:
            thread = await client.threads.create(
                metadata=metadata,
                thread_id=thread_id,
                if_exists=if_exists,
                graph_id=graph_id,
                supersteps=supersteps,
                ttl=ttl
            )
            return thread
        except Exception as e:
            logger.error(f"Error creating thread: {e}", exc_info=True)
            raise

    async def get_thread(self, thread_id: str) -> Dict[str, Any]:
        """
        Get details of a thread by its ID.

        Args:
            thread_id: The ID of the thread you want to retrieve.

        Returns:
            Thread object as dict.
        """
        client = await self._get_client()
        return await client.threads.get(thread_id)

    async def update_thread(
        self,
        thread_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        ttl: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Update a thread’s metadata or TTL.

        Args:
            thread_id: The ID of the thread to update.
            metadata: New or updated metadata dict.
            ttl: (Optional) new TTL or time-to-live settings.

        Returns:
            The updated thread object.
        """
        client = await self._get_client()
        return await client.threads.update(
            thread_id=thread_id,
            metadata=metadata,
            ttl=ttl
        )

    async def delete_thread(self, thread_id: str) -> None:
        """
        Delete a thread (and optionally its state).

        Args:
            thread_id: The ID of the thread to delete.

        Returns:
            None
        """
        client = await self._get_client()
        await client.threads.delete(thread_id)

    async def search_threads(
        self,
        metadata: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for threads matching filter criteria.

        Args:
            metadata: Filter threads by metadata keys/values.
            status: Filter by thread status (e.g. "idle", "busy", "error").
            limit: Max number of threads to return.
            offset: Offset for pagination.
            sort_by: Sort by one of the thread fields (thread_id, status, created_at, updated_at) :contentReference[oaicite:1]{index=1}
            sort_order: "asc" or "desc".

        Returns:
            A list of thread dicts.
        """
        client = await self._get_client()
        return await client.threads.search(
            metadata=metadata,
            status=status,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order
        )

    async def get_thread_history(
        self,
        thread_id: str,
        checkpoint: Optional[Any] = None,
        limit: Optional[int] = 10,
        before: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the state history of a thread.

        Args:
            thread_id: The thread to fetch history for.
            checkpoint: (Optional) checkpoint context to scope history.
            limit: Max states to return.
            before: Only states before a given checkpoint/time.
            metadata: Optional filtering by metadata.

        Returns:
            A list of state snapshots for the thread.
        """
        client = await self._get_client()
        return await client.threads.get_history(
            thread_id=thread_id,
            checkpoint=checkpoint,
            limit=limit,
            before=before,
            metadata=metadata
        )