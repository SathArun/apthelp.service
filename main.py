"""
Start: uvicorn app:app --reload --port 8000
Env required: OPENAI_API_KEY, WEAVIATE_URL, WEAVIATE_API_KEY(optional)
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import weaviate
from weaviate.classes.init import Auth

from openai import OpenAI

from dotenv import load_dotenv
load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
WEAVIATE_URL = os.environ.get("WEAVIATE_URL")
WEAVIATE_API_KEY = os.environ.get("WEAVIATE_API_KEY")

app = FastAPI()
#client = weaviate.Client(WEAVIATE_URL, auth_client_secret=weaviate.AuthApiKey(api_key=WEAVIATE_API_KEY) if WEAVIATE_API_KEY else None)
client = weaviate.connect_to_weaviate_cloud(
    cluster_url=WEAVIATE_URL,
    auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
)
openai = OpenAI(api_key=OPENAI_API_KEY)

class QueryRequest(BaseModel):
    question: str
    top_k: int = 6

class QueryResponse(BaseModel):
    answer: str
    sources: list
    confidence: float

@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"message": "Backend is running."}

@app.get("/health")
async def health():
    return {"status": "ok"}


def semantic_search(question, top_k=6):
    # Embed the question
    resp = openai.embeddings.create(model="text-embedding-3-small", input=question)
    qvec = resp.data[0].embedding
    collection = client.collections.get("LegalChunk")
    results = collection.query.near_vector(
        near_vector=qvec,
        limit=top_k,
        return_properties=["text", "source_url", "title", "page", "date", "doc_type", "gov_order", "court_level"]
    )
    hits = []
    for h in results.objects:
        hits.append({
            'text': h.properties.get('text'),
            'source_url': h.properties.get('source_url'),
            'title': h.properties.get('title'),
            'page': h.properties.get('page'),
            'date': h.properties.get('date'),
            'doc_type': h.properties.get('doc_type')
        })
    return hits


def build_prompt(question, hits):
    system = (
        "You are a legal research assistant specialized in Tamil Nadu apartment law."
        "Answer concisely. When quoting statutory or judgment text, include exact quotes and cite source title, date and page."
        "If uncertain, say so and provide the chunk text used as evidence.\n\n"
    )
    context_parts = []
    for i, h in enumerate(hits, start=1):
        context_parts.append(f"[DOC {i}] Title: {h['title']} | Date: {h.get('date')} | Page: {h.get('page')} | URL: {h.get('source_url')}\n{h['text']}")
    prompt = system + "\n\nContext:\n" + "\n\n".join(context_parts) + f"\n\nUser question: {question}\n\nAnswer:" 
    return prompt


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    try:
        hits = semantic_search(req.question, req.top_k)
        if not hits:
            return {"answer": "No relevant documents found.", "sources": [], "confidence": 0.0}
        prompt = build_prompt(req.question, hits)
        # Call LLM for completion
        completion = openai.responses.create(model="gpt-4o-mini", input=prompt, max_output_tokens=800)
        answer_text = completion.output_text if hasattr(completion, 'output_text') else completion.get('output', [{}])[0].get('content', [{}])[0].get('text','')
        # Build sources for response
        sources = [ {"title": h['title'], "url": h['source_url'], "page": h['page']} for h in hits ]
        return {"answer": answer_text, "sources": sources, "confidence": 0.85}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
