"""
retrieve.py

Given a natural-language question, embeds it with the same model used in
embed_store.py and searches ChromaDB for the most semantically similar
code chunks.
"""

import chromadb
from sentence_transformers import SentenceTransformer

DB_DIR = "chroma_db"
COLLECTION_NAME = "code_chunks"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_model = None
_collection = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=DB_DIR)
        _collection = client.get_collection(COLLECTION_NAME)
    return _collection


def retrieve(query: str, top_k: int = 5):
    """
    Returns a list of dicts: { document, metadata, distance }
    sorted by relevance (most relevant first).
    """
    model = _get_model()
    collection = _get_collection()

    query_embedding = model.encode([query]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
    )

    hits = []
    for i in range(len(results["ids"][0])):
        hits.append({
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })

    return hits


if __name__ == "__main__":
    # Quick manual test
    query = input("Ask a question about the codebase: ")
    hits = retrieve(query)

    print(f"\nTop {len(hits)} relevant chunks:\n")
    for h in hits:
        m = h["metadata"]
        print(f"- {m['file']}:{m['start_line']}-{m['end_line']}  ({m['type']} {m['name']})  distance={h['distance']:.4f}")