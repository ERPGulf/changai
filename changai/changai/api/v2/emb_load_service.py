"""ChangAI embedding service: loads the embedding model once and serves embeddings over
HTTP, so web workers and rebuild jobs don't each load torch and the model.

Run (bind to localhost only):
    CHANGAI_EMBEDDING_MODEL_PATH=/path/to/sites/<site>/private/files/changai_model \
    env/bin/uvicorn changai.changai.api.v2.emb_load_service:app --host 127.0.0.1 --port 8001 --workers 1

Then set "changai_embedding_service_url": "http://127.0.0.1:8001" in site_config.json.
"""
import os
import threading
from typing import List

from fastapi import FastAPI, HTTPException
from langchain_huggingface import HuggingFaceEmbeddings
from pydantic import BaseModel

MODEL_PATH = os.environ.get("CHANGAI_EMBEDDING_MODEL_PATH")
MAX_BATCH = 256

app = FastAPI()

# Same settings as retrieve.get_embedding_engine(), so vectors match indexes built in-process
embedding_model = HuggingFaceEmbeddings(
    model_name=MODEL_PATH,
    model_kwargs={
        "device": "cpu",
        "trust_remote_code": True,
    },
    encode_kwargs={
        "normalize_embeddings": True,
    },
)

# warmup during service startup
embedding_model.embed_query("changai warmup")

# FastAPI runs sync endpoints in a thread pool; one encode at a time keeps memory flat
_encode_lock = threading.Lock()


class EmbedRequest(BaseModel):
    text: str


class EmbedBatchRequest(BaseModel):
    texts: List[str]


@app.get("/health")
def health():
    return {"ok": True, "model_loaded": True, "model_path": MODEL_PATH}


@app.post("/embed")
def embed(req: EmbedRequest):
    with _encode_lock:
        vector = embedding_model.embed_query(req.text)
    return {"embedding": vector}


@app.post("/embed_batch")
def embed_batch(req: EmbedBatchRequest):
    if len(req.texts) > MAX_BATCH:
        raise HTTPException(status_code=413, detail=f"At most {MAX_BATCH} texts per request")
    with _encode_lock:
        vectors = embedding_model.embed_documents(req.texts)
    return {"embeddings": vectors}
