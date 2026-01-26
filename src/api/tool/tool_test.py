from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import spacy

# Load the spaCy model
nlp = spacy.load("en_core_web_sm")

# FastAPI app
app = FastAPI(title="Question Generator API")

# Pydantic model for request
class TextRequest(BaseModel):
    text: str

# Function to generate questions (your code)
def generate_questions(text: str) -> List[str]:
    doc = nlp(text)
    questions = []
    
    for sent in doc.sents:
        # Find the main root verb and its subject
        root = next((token for token in sent if token.dep_ == "ROOT"), None)
        subj = next((c for c in root.children if c.dep_ in ("nsubj", "nsubjpass")), None)

        if root and subj:
            # Get the full subject phrase (e.g., "Artificial intelligence")
            subject_phrase = "".join(t.text_with_ws for t in subj.subtree).strip()
            
            # Form simple "What" questions based on the root verb
            # Example: "What continues evolving...?" or "What drive improvements...?"
            # We use root.head logic or children to capture context
            predicate = "".join(t.text_with_ws for t in root.subtree if t != subj).strip()
            
            if predicate:
                questions.append(f"What {predicate.strip(' .')}?")

        # Backup: Extract Noun Chunks for "What is..." questions
        # This covers definitions in technical text
        for chunk in doc.noun_chunks:
            if len(chunk.text.split()) > 1: # Only multi-word phrases
                questions.append(f"What is {chunk.text}?")

    return list(set(questions))

    

# FastAPI endpoint
@app.post("/generate-questions", response_model=List[str])
def generate_questions_endpoint(request: TextRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    questions = generate_questions(request.text)
    return questions

# To run: uvicorn main:app --reload
