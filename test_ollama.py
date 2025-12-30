import time
import logging
from langchain_ollama import OllamaEmbeddings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_ollama_embeddings():
    print("\n--- Ollama Embedding Model Test ---")
    
    model_name = "nomic-embed-text:latest"
    print(f"Testing model: {model_name}")
    
    try:    
        # Initialize embeddings
        start_time = time.time()
        embeddings = OllamaEmbeddings(model=model_name, num_gpu=0)
        print(f"Initialization took: {time.time() - start_time:.2f} seconds")
        
        # Test single query embedding
        query = "What are the latest advancements in AI in 2025?"
        print(f"\n1. Testing embed_query with: '{query}'")
        start_time = time.time()
        query_vector = embeddings.embed_query(query)
        print(f"   Success! Vector length: {len(query_vector)}")
        print(f"   Success! Vector: {query_vector}")

        print(f"   Time taken: {time.time() - start_time:.2f} seconds")
        
        # Test batch document embedding
        docs = [
            "Artificial Intelligence is evolving rapidly.",
            "Large Language Models are becoming more efficient.",
            "Agentic workflows are the next big thing in software development."
        ]
        print(f"\n2. Testing embed_documents with {len(docs)} documents")
        start_time = time.time()
        doc_vectors = embeddings.embed_documents(docs)
        print(f"   Success! Created {len(doc_vectors)} vectors.")
        print(f"   Time taken: {time.time() - start_time:.2f} seconds")
        
        print("\n✅ Ollama embedding model is working correctly!")
        
    except Exception as e:
        print(f"\n❌ Error testing Ollama: {str(e)}")
        print("\nTroubleshooting tips:")
        print("1. Ensure Ollama is running (`ollama serve`)")
        print(f"2. Ensure the model is pulled (`ollama pull {model_name}`)")
        print("3. Check if Ollama is reachable at http://localhost:11434")

if __name__ == "__main__":
    test_ollama_embeddings()
