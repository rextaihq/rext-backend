from typing import List, Union

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.api.lib.logger import auto_logger

logger = auto_logger()


def split_data(
    documents: Union[List[Document], str], chunk_size: int = 1000, overlap: int = 200
) -> List[Document]:
    """
    Splits text or Document objects into semantic chunks for vector embeddings.

    Following LangChain v1.0 best practices (Released Oct 2025):
    - Uses RecursiveCharacterTextSplitter for semantic splitting
    - Preserves document metadata across chunks
    - Adds chunk-specific metadata for tracking
    - Handles both raw strings and Document objects

    RecursiveCharacterTextSplitter splits on separators in order:
    1. "\n\n" (paragraphs) - preserves semantic structure
    2. "\n" (lines) - maintains readability
    3. " " (words) - keeps words intact
    4. "" (characters) - fallback for very long words

    Args:
        documents: Input text string or list of Document objects to split
        chunk_size: Maximum size of each text chunk in characters
                   Default: 1000 (optimal for most retrieval tasks)
        overlap: Number of overlapping characters between chunks
                Default: 200 (20% overlap maintains context continuity)

    Returns:
        List of Document objects with:
            - page_content: The chunked text content
            - metadata: Original metadata plus:
                - chunk_id: Zero-based index of chunk
                - total_chunks: Total number of chunks from this document
                - length: Character count of this chunk

    Raises:
        ValueError: If documents is neither a string nor List[Document]
        Exception: If text splitting fails

    Examples:
        >>> # Split a string
        >>> chunks = split_data("Long text...", chunk_size=500, overlap=100)
        >>> print(len(chunks))
        3

        >>> # Split Document objects
        >>> from langchain_core.documents import Document
        >>> docs = [Document(page_content="Text", metadata={"source": "file.txt"})]
        >>> chunks = split_data(docs)
        >>> print(chunks[0].metadata)
        {'source': 'file.txt', 'chunk_id': 0, 'total_chunks': 1, 'length': 4}

    Note:
        Chunk size of 1000 with 200 overlap is optimal for:
        - BAAI/bge-small-en embeddings (512 token context window)
        - Most retrieval tasks balancing precision vs. context
        - ~150-200 words per chunk (typical English text)
    """
    try:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)

        chunked_docs = []

        if isinstance(documents, list) and all(isinstance(doc, Document) for doc in documents):
            # Case 1: Input is a list of Documents
            for doc in documents:
                chunks = text_splitter.split_text(doc.page_content)
                for idx, chunk in enumerate(chunks):
                    chunked_docs.append(
                        Document(
                            page_content=chunk,
                            metadata={
                                **doc.metadata,
                                "chunk_id": idx,
                                "total_chunks": len(chunks),
                                "length": len(chunk),
                            },
                        )
                    )
        elif isinstance(documents, str):
            # Case 2: Input is a plain string
            chunks = text_splitter.create_documents([documents])
            for idx, doc in enumerate(chunks):
                doc.metadata.update(
                    {"chunk_id": idx, "total_chunks": len(chunks), "length": len(doc.page_content)}
                )
                chunked_docs.append(doc)
        else:
            raise ValueError("documents must be either a string or List[Document].")

        logger.info(f"Data split successfully! Total chunks: {len(chunked_docs)}")
        return chunked_docs

    except ValueError:
        # Re-raise validation errors (e.g., invalid input type) as-is
        raise
    except Exception as e:
        logger.error(f"Failed to split documents into chunks: {e}", exc_info=True)
        return []
