from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from typing import List, Union

from src.api.lib.logger import auto_logger

logger = auto_logger()

def split_data(
    documents: Union[List[Document], str],
    chunk_size: int = 1000,
    overlap: int = 200
) -> List[Document]:
    """
    Splits text(s) or Document(s) into smaller chunks for efficient retrieval and embedding.

    Args:
        documents (Union[List[Document], str]): Input text or list of Document objects.
        chunk_size (int, optional): Maximum size of each text chunk. Defaults to 1000.
        overlap (int, optional): Number of overlapping characters between chunks. Defaults to 200.

    Returns:
        List[Document]: A list of Document objects with:
            - page_content (str): The chunked text content.
            - metadata (dict): Includes:
                - "source" (if available),
                - "chunk_id",
                - "total_chunks",
                - "length".
    """
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap
        )

        chunked_docs = []

        if isinstance(documents, list) and all(isinstance(doc, Document) for doc in documents):
            # Case 1: Input is a list of Documents
            for doc in documents:
                chunks = text_splitter.split_text(doc.page_content)
                for idx, chunk in enumerate(chunks):
                    chunked_docs.append(Document(
                        page_content=chunk,
                        metadata={
                            **doc.metadata,
                            "chunk_id": idx,
                            "total_chunks": len(chunks),
                            "length": len(chunk)
                        }
                    ))
        elif isinstance(documents, str):
            # Case 2: Input is a plain string
            chunks = text_splitter.create_documents([documents])
            for idx, doc in enumerate(chunks):
                doc.metadata.update({
                    "chunk_id": idx,
                    "total_chunks": len(chunks),
                    "length": len(doc.page_content)
                })
                chunked_docs.append(doc)
        else:
            raise ValueError("documents must be either a string or List[Document].")

        logger.info(f"Data split successfully! Total chunks: {len(chunked_docs)}")
        return chunked_docs

    except Exception as e:
        logger.info("Error:", str(e))
        return []