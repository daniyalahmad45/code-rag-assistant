"""
retrieve.py

Given a natural-language question, embeds it with the same model used in
embed_store.py and searches ChromaDB for the most semantically similar
code chunks. If the question mentions a specific filename, retrieval is
filtered to that file so all its chunks are considered, not just whatever
happens to be semantically closest.
"""

import re

from embed_store import COLLECTION_NAME, get_client, get_model


def extract_filename(query: str):
    """Detect a mentioned .py filename in the question, e.g. 'attendance.py'."""
    match = re.search(r"[\w\-/]+\.py", query)
    return match.group(0) if match else None


def retrieve(query: str, top_k: int = 5, file_filter: str = None, collection_name: str = COLLECTION_NAME):
    """
    Returns a list of dicts: { document, metadata, distance }
    sorted by relevance (most relevant first).

    If file_filter is set, only chunks from that file are considered.
    If file_filter is None, it's auto-detected from the query text.
    collection_name picks which indexed repository to search.
    """
    model = get_model()
    collection = get_client().get_collection(collection_name)

    if file_filter is None:
        file_filter = extract_filename(query)

    query_embedding = model.encode([query]).tolist()

    query_kwargs = {
        "query_embeddings": query_embedding,
        "n_results": top_k,
    }
    if file_filter:
        query_kwargs["where"] = {"file": file_filter}

    results = collection.query(**query_kwargs)

    # A mentioned filename may not match a stored path exactly (e.g. "utils.py"
    # vs "src/utils.py"), so fall back to searching the whole repo.
    if file_filter and not results["ids"][0]:
        del query_kwargs["where"]
        results = collection.query(**query_kwargs)

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