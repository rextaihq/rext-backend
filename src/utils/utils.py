# File: rext-backend/src/utils/utils.py
# Replace the entire file:

from typing import List

from langchain_community.document_loaders import PyMuPDFLoader, CSVLoader
from langchain_core.documents import Document
from src.utils.splitter import split_data

from src.api.lib.logger import auto_logger

logger = auto_logger()

def load_split_file_data(file_path: str) -> List[Document]:
    """Load a file and return its content as a list of Document chunks."""
    try:
        # load file
        if file_path.endswith(".pdf"):
            loader = PyMuPDFLoader(file_path)
            documents = loader.load()
        elif file_path.endswith(".csv"):
            loader = CSVLoader(file_path)
            documents = loader.load()
        else:
            documents = []

        if not documents:
            raise ValueError("No documents loaded")

        # split into chunks
        chunks_data = split_data(documents=documents, chunk_size=1000, overlap=200)

        return chunks_data

    except Exception as e:
        logger.error(f"Error loading file {file_path}: {e}", exc_info=True)
        return []       
