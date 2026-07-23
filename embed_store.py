"""
embed_store.py

Loads chunks.json (produced by ingest.py), embeds each chunk using a
local sentence-transformers model (no API cost), and stores them in a
persistent ChromaDB collection for semantic search.

Run this after ingest.py.
"""

import json
import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = "chunks.json"
DB_DIR = "chroma_db"
COLLECTION_NAME = "code_chunks"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # small, fast, free, runs locally


def load_chunks(path=CHUNKS_FILE):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_document_text(chunk):
    """
    What gets embedded. Include the file/name/type as light context so the
    embedding captures more than just raw code syntax.
    """
    return f"File: {chunk['file']}\n{chunk['type']} {chunk['name']}\n\n{chunk['code']}"


def main():
    print("Loading chunks...")
    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks.")

    print(f"Loading embedding model '{EMBEDDING_MODEL}' (first run downloads it)...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    print("Embedding chunks...")
    documents = [build_document_text(c) for c in chunks]
    embeddings = model.encode(documents, show_progress_bar=True).tolist()

    print("Connecting to ChromaDB...")
    client = chromadb.PersistentClient(path=DB_DIR)

    # Start fresh each time this script runs, so re-ingesting doesn't duplicate
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(COLLECTION_NAME)

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

    print("Storing in ChromaDB...")
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    print(f"\nDone. Stored {len(chunks)} chunks in ChromaDB collection '{COLLECTION_NAME}' at ./{DB_DIR}")


if __name__ == "__main__":
    main()