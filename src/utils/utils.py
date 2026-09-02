# File: rext-backend/src/utils/utils.py
# Replace the entire file:

from pathlib import Path
from typing import List

from langchain_community.document_loaders import CSVLoader, PyMuPDFLoader
from langchain_core.documents import Document

from src.api.lib.logger import auto_logger
from src.utils.splitter import split_data

logger = auto_logger()

import os  # noqa: E402 -- intentional: avoids a circular import
import tempfile  # noqa: E402 -- intentional: avoids a circular import

from src.utils.storage import storage_service  # noqa: E402 -- intentional: avoids a circular import


def load_split_file_data(file_path: str) -> List[Document]:
    """Load a file and return its content as a list of Document chunks."""
    temp_file = None
    try:
        # Check if file_path is a local file or a MinIO key
        current_path = Path(file_path)
        if not current_path.exists():
            # Assume it's a MinIO key, download to temp file
            suffix = current_path.suffix
            fd, temp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            temp_file = temp_path
            storage_service.download_file(file_path, temp_path)
            load_path = temp_path
        else:
            load_path = file_path

        # load file
        if load_path.endswith(".pdf"):
            loader = PyMuPDFLoader(load_path)
            documents = loader.load()
        elif load_path.endswith(".csv"):
            loader = CSVLoader(load_path)
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
    finally:
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)
