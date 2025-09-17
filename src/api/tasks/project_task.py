from langchain_community.document_loaders import PyMuPDFLoader, CSVLoader
from sqlalchemy.orm import Session
from src.utils.splitter import split_data
from src.nodes.vectorStore.buildVectorStore import build_vector_store
from src.api.database.database import get_db

def project_task(file_path: str, project_id):
    db_gen = get_db()
    db: Session = next(db_gen)
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

        # add to vector store
        build_vector_store(blog_context=chunks_data)
       
    except Exception as e:
        # mark project as failed
        project = db.query(Projects).filter(Projects.id == project_id).first()
        if project:
            project.status = "failed"
            db.commit()
        print(f"⚠️ Error processing project {project_id}: {e}")
    finally:
        db.close()
