"""
embed_store.py

Loads chunks.json (produced by ingest.py), embeds each chunk using a
local sentence-transformers model (no API cost), and stores them in a
persistent ChromaDB collection for semantic search.

Run this after ingest.py. The app also calls store_chunks() directly to
index repositories that users add at runtime.
"""

import json
import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = "chunks.json"
DB_DIR = "chroma_db"
COLLECTION_NAME = "code_chunks"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # small, fast, free, runs locally
BATCH_SIZE = 1000  # ChromaDB caps how many records one add() call can take

_model = None
_client = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=DB_DIR)
    return _client


def load_chunks(path=CHUNKS_FILE):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_document_text(chunk):
    """
    What gets embedded. Include the file/name/type as light context so the
    embedding captures more than just raw code syntax.
    """
    return f"File: {chunk['file']}\n{chunk['type']} {chunk['name']}\n\n{chunk['code']}"


def store_chunks(chunks, collection_name=COLLECTION_NAME, metadata=None, show_progress=False):
    """Embed chunks and (re)create a ChromaDB collection holding them."""
    documents = [build_document_text(c) for c in chunks]
    embeddings = get_model().encode(documents, show_progress_bar=show_progress).tolist()

    client = get_client()

    # Start fresh each time, so re-ingesting doesn't duplicate
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(collection_name, metadata=metadata)

    ids = [f"chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "file": c["file"],
            "name": c["name"],
            "type": c["type"],
            "start_line": c["start_line"],
            "end_line": c["end_line"],
        }
        for c in chunks
    ]

    for start in range(0, len(chunks), BATCH_SIZE):
        end = start + BATCH_SIZE
        collection.add(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )

    return collection


def main():
    print("Loading chunks...")
    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks.")

    print(f"Embedding with '{EMBEDDING_MODEL}' (first run downloads it) and storing in ChromaDB...")
    store_chunks(chunks, metadata={"display_name": "Sample: face attendance"}, show_progress=True)

    print(f"\nDone. Stored {len(chunks)} chunks in ChromaDB collection '{COLLECTION_NAME}' at ./{DB_DIR}")


if __name__ == "__main__":
    main()
