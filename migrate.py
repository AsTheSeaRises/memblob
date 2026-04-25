"""One-shot migration between embedding backends.

Use this when switching MEMBLOB_BACKEND between 'local' and 'api' (or vice versa).
The two backends use different embedding models with incompatible vector spaces,
so existing memories must be re-embedded after a switch.

This script pulls all stored fact texts, wipes the collection, and re-adds them
using whichever backend is currently active — no re-extraction needed.

Run: `.venv/bin/python migrate.py`
Requires: .env configured for the NEW backend you are migrating TO.
"""

import os
import chromadb
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from memory import create_memory, DEFAULT_DB_PATH

COLLECTION = "memories"


def main() -> None:
    chroma = chromadb.PersistentClient(path=DEFAULT_DB_PATH)

    old = chroma.get_or_create_collection(COLLECTION)
    dump = old.get()
    docs = dump["documents"]
    metadatas = dump["metadatas"]
    ids = dump["ids"]
    print(f"Found {len(docs)} memories to migrate.")

    if not docs:
        print("Nothing to migrate.")
        return

    chroma.delete_collection(COLLECTION)

    mem = create_memory(DEFAULT_DB_PATH)
    mem.collection.upsert(documents=docs, metadatas=metadatas, ids=ids)
    backend = os.environ.get("MEMBLOB_BACKEND", "api")
    print(f"Migrated {len(docs)} memories using '{backend}' backend.")


if __name__ == "__main__":
    main()
