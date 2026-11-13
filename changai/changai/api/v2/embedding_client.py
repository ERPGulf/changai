from typing import Any, Dict, List

import frappe
import requests
from frappe import _
from langchain_core.embeddings import Embeddings

# Texts per request: enough to amortise the HTTP call, small enough for the service's memory
BATCH_SIZE = 64
TIMEOUT_SEC = 120


class EmbeddingServiceClient(Embeddings):
    """Embeddings from the ChangAI embedding service (emb_load_service.py).

    Used when site_config has changai_embedding_service_url, so web workers and rebuild
    jobs never load torch or the model themselves.
    """

    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            res = requests.post(f"{self.url}{path}", json=payload, timeout=TIMEOUT_SEC)
            res.raise_for_status()
            return res.json()
        except requests.RequestException:
            frappe.log_error(frappe.get_traceback(), "ChangAI Embedding Service Error")
            frappe.throw(
                _("The ChangAI embedding service at {0} is not reachable. Ask your administrator to check that it is running.").format(self.url),
                title=_("Embedding Service Unavailable"),
            )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = list(texts[start:start + BATCH_SIZE])
            vectors.extend(self._post("/embed_batch", {"texts": batch})["embeddings"])
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self._post("/embed", {"text": text})["embedding"]
