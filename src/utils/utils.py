import os
from typing import List

from langchain_community.document_loaders import (
    PyMuPDFLoader,
    CSVLoader,
    Docx2txtLoader,
    TextLoader,
)
from langchain_community.document_loaders.excel import UnstructuredExcelLoader
from langchain_core.documents import Document

from src.utils.splitter import split_data
from src.api.lib.logger import auto_logger

logger = auto_logger()

# Map file extensions to their corresponding LangChain document loader classes.
# Each loader converts a file into a list of LangChain Document objects.
LOADER_MAP: dict[str, type] = {
    ".pdf": PyMuPDFLoader,
    ".csv": CSVLoader,
    ".docx": Docx2txtLoader,
    ".doc": Docx2txtLoader,
    ".txt": TextLoader,
    ".xlsx": UnstructuredExcelLoader,
    ".xls": UnstructuredExcelLoader,
}

SUPPORTED_EXTENSIONS = set(LOADER_MAP.keys())


def load_split_file_data(
    file_path: str,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> List[Document]:
    """
    Load a file, extract its text content, and split into chunks for vector embedding.

    Supports: PDF, CSV, DOCX, DOC, TXT, XLSX, XLS.

    Args:
        file_path: Absolute path to the file on disk.
        chunk_size: Maximum characters per chunk (default 1000).
        overlap: Overlapping characters between consecutive chunks (default 200).

    Returns:
        List of LangChain Document objects (chunks), each with page_content and metadata.

    Raises:
        ValueError: If the file extension is not supported or no content could be extracted.
    """
    ext = os.path.splitext(file_path)[1].lower()
    loader_cls = LOADER_MAP.get(ext)

    if loader_cls is None:
        raise ValueError(
            f"Unsupported file extension '{ext}'. "
            f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        loader = loader_cls(file_path)
        documents = loader.load()
    except Exception as e:
        logger.error(f"Failed to load file {file_path} with {loader_cls.__name__}: {e}")
        raise ValueError(f"Failed to extract content from file: {e}") from e

    if not documents:
        raise ValueError(f"No content could be extracted from {file_path}")

    chunks_data = split_data(documents=documents, chunk_size=chunk_size, overlap=overlap)

    if not chunks_data:
        raise ValueError(f"File content was extracted but produced zero chunks: {file_path}")

    logger.info(
        f"File loaded and split successfully",
        extra={
            "file_path": file_path,
            "extension": ext,
            "documents_loaded": len(documents),
            "chunks_produced": len(chunks_data),
        },
    )

    return chunks_data