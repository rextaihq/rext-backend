from langchain_community.document_loaders import PyMuPDFLoader, CSVLoader
from src.utils.splitter import split_data

def load_split_file_data(file_path: str) -> str:
    """Load and return the content of a file as text."""
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
        chunks_data = split_data(documents=documents,chunk_size=1000,overlap=200)

        return chunks_data
       
    except Exception as e:
        print(f"⚠️ Error loading file {file_path}: {e}")
        return []
