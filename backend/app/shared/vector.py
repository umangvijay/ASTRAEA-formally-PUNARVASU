"""Vector memory — the semantic half of LOOM.

Every context item is embedded (MiniLM when available, deterministic hashed
bigrams offline) and stored in a persistent Chroma collection with full
metadata (tenant, origin module, kind, timestamp). Modules get RAG over shared
memory via `semantic_search` — the anti-re-onboarding promise, now queryable.

Backend: chromadb PersistentClient under data/chroma. Embeddings are computed
by us and passed explicitly, so no network round-trips at query time.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import threading
from typing import Any

from app.config import settings

logger = logging.getLogger("vector")

_client = None
_client_lock = threading.Lock()
_embedder = None
_embedder_kind = "hash"
_EMBED_DIM = 384
_COLLECTION = "loom"


def _get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                try:
                    import chromadb

                    path = str(settings.data_dir / "chroma")
                    settings.data_dir.mkdir(parents=True, exist_ok=True)
                    _client = chromadb.PersistentClient(path=path)
                except Exception as exc:  # noqa: BLE001 — chroma is optional on Cloud Run
                    logger.warning("chroma unavailable (%s) — vector memory disabled", str(exc)[:80])
                    _client = False
    return _client if _client is not False else None


# ── embeddings ─────────────────────────────────────────────────────
class HashedEmbedder:
    """Deterministic offline embeddings: normalized bag of hashed word+bigram
    features. Not as sharp as MiniLM, works with zero deps and zero network.

    Dimension matches MiniLM (384) so both backends share a vector space contract;
    collections are additionally namespaced by embedder kind (bug #13)."""

    dim = _EMBED_DIM  # 384 — same as all-MiniLM-L6-v2

    @staticmethod
    def _feats(text: str) -> dict[int, float]:
        words = re.findall(r"[a-z0-9]+", (text or "").lower())
        feats: dict[int, float] = {}
        for w in words:
            for gram in (w, *[w[i:i + 2] for i in range(len(w) - 1)]):
                h = int(hashlib.md5(gram.encode()).hexdigest(), 16)
                idx = h % _EMBED_DIM
                feats[idx] = feats.get(idx, 0.0) + 1.0 / (1.0 + math.log(1 + len(w)))
        return feats

    def encode(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            norm = 0.0
            for idx, w in self._feats(text).items():
                vec[idx] = w
                norm += w * w
            if norm > 0:
                vec = [v / math.sqrt(norm) for v in vec]
            out.append(vec)
        return out


def get_embedder():
    """MiniLM (neural, spec-recommended) when loadable; hashed fallback otherwise."""
    global _embedder, _embedder_kind
    if _embedder is None:
        import os

        # Cloud Run OOM-kills a 512Mi instance that loads torch/MiniLM at boot.
        force_hash = (
            os.environ.get("K_SERVICE")
            or os.environ.get("ASTRAEA_EMBEDDER", "").lower() == "hash"
            or settings.env == "production"
        )
        if not force_hash:
            try:
                from sentence_transformers import SentenceTransformer

                _embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                _embedder_kind = "minilm"
            except Exception as exc:  # noqa: BLE001 — offline / weights missing
                logger.warning("MiniLM unavailable (%s) — using hashed embeddings", str(exc)[:80])
                _embedder = HashedEmbedder()
                _embedder_kind = "hash"
        if _embedder is None:
            _embedder = HashedEmbedder()
            _embedder_kind = "hash"
    return _embedder


def embed_kind() -> str:
    get_embedder()
    return _embedder_kind


def _embed(texts: list[str]) -> list[list[float]]:
    emb = get_embedder()
    if _embedder_kind == "minilm":
        return [v.tolist() for v in emb.encode(texts, normalize_embeddings=True)]
    return emb.encode(texts)


# ── collection ops ─────────────────────────────────────────────────
def _collection():
    # Namespace by embedder kind so a MiniLM<->hash failover (different processes,
    # missing weights) can never write mismatched dims into one collection (bug #13).
    client = _get_client()
    if client is None:
        raise RuntimeError("chroma unavailable")
    name = f"{_COLLECTION}_{embed_kind()}"
    return client.get_or_create_collection(
        name, metadata={"hnsw:space": "cosine"}
    )


def index_item(item_id: str, tenant_id: str, text: str, metadata: dict[str, Any]) -> bool:
    """Upsert one item's vector. Never raises — indexing must not break writes."""
    try:
        col = _collection()
        meta = {"tenant_id": tenant_id, **metadata}
        col.upsert(ids=[item_id], embeddings=_embed([text[:4000]]), metadatas=[meta],
                   documents=[text[:4000]])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector index failed for %s: %s", item_id[:8], str(exc)[:120])
        return False


def delete_item(item_id: str) -> None:
    try:
        _collection().delete(ids=[item_id])
    except Exception:  # noqa: BLE001
        pass


def semantic_search(tenant_id: str, query: str, *, k: int = 5,
                    module: str | None = None,
                    origin_module: str | None = None) -> list[dict[str, Any]]:
    """Top-k shared-memory hits for one tenant (optionally filtered to items
    the given module may see — module filter is applied post-hoc on share_with)."""
    where: dict[str, Any] = {"tenant_id": tenant_id}
    if origin_module:
        where["origin_module"] = origin_module
    try:
        col = _collection()
        res = col.query(query_embeddings=_embed([query]), n_results=min(k * 3, 50),
                        where=where, include=["metadatas", "documents", "distances"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector search failed: %s", str(exc)[:120])
        return []
    hits: list[dict[str, Any]] = []
    for iid, meta, doc, dist in zip(
        res["ids"][0], res["metadatas"][0], res["documents"][0], res["distances"][0]
    ):
        hits.append({
            "item_id": iid, "score": round(1.0 - float(dist), 4),
            "metadata": meta, "document": (doc or "")[:400],
        })
    return hits[:k]


async def aindex_item(item_id: str, tenant_id: str, text: str, metadata: dict[str, Any]) -> bool:
    return await asyncio.to_thread(index_item, item_id, tenant_id, text, metadata)


async def asearch(tenant_id: str, query: str, *, k: int = 5,
                  module: str | None = None,
                  origin_module: str | None = None) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        semantic_search, tenant_id, query, k=k, module=module, origin_module=origin_module
    )
