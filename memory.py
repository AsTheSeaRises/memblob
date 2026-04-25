import chromadb
from chromadb.utils.embedding_functions.ollama_embedding_function import OllamaEmbeddingFunction
import ollama
import json
import hashlib

EXTRACT_PROMPT = """Extract key facts from this conversation as a JSON array of short statements.
Only extract concrete, factual information worth remembering long-term (names, preferences, tools, decisions).
Return ONLY a JSON array of strings with no markdown or explanation.

Conversation:
{text}"""

EMBED_MODEL = "nomic-embed-text"
EXTRACT_MODEL = "gemma4:e2b"
DEDUP_DISTANCE = 0.08  # cosine distance; facts closer than this are treated as duplicates


class SimpleMemory:
    def __init__(self, db_path=os.path.expanduser("~/.memblob/memory_db")):
        ef = OllamaEmbeddingFunction(
            url="http://localhost:11434/api/embeddings",
            model_name=EMBED_MODEL,
        )
        self.chroma = chromadb.PersistentClient(path=db_path)
        self.collection = self.chroma.get_or_create_collection(
            "memories",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    def _is_duplicate(self, fact: str, user_id: str) -> bool:
        if self.collection.count() == 0:
            return False
        results = self.collection.query(
            query_texts=[fact],
            where={"user_id": user_id},
            n_results=1,
        )
        if results["distances"] and results["distances"][0]:
            return results["distances"][0][0] < DEDUP_DISTANCE
        return False

    def add(self, text: str, user_id: str = "default") -> list[str]:
        resp = ollama.chat(
            model=EXTRACT_MODEL,
            messages=[{"role": "user", "content": EXTRACT_PROMPT.format(text=text)}],
        )
        raw = resp["message"]["content"].strip()
        # Strip markdown code fences that models sometimes emit
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            facts = json.loads(raw)
        except json.JSONDecodeError:
            return []

        stored = []
        for fact in facts:
            if not isinstance(fact, str) or not fact.strip():
                continue
            if not self._is_duplicate(fact, user_id):
                doc_id = f"{user_id}_{hashlib.md5(fact.encode()).hexdigest()}"
                self.collection.upsert(
                    documents=[fact],
                    metadatas=[{"user_id": user_id}],
                    ids=[doc_id],
                )
                stored.append(fact)
        return stored

    def search(self, query: str, user_id: str = "default", n: int = 5) -> list[str]:
        count = self.collection.count()
        if count == 0:
            return []
        results = self.collection.query(
            query_texts=[query],
            where={"user_id": user_id},
            n_results=min(n, count),
        )
        return results["documents"][0] if results["documents"] else []

    def list_all(self, user_id: str = "default") -> list[str]:
        return self.collection.get(where={"user_id": user_id})["documents"]

    def delete(self, fact: str, user_id: str = "default") -> None:
        doc_id = f"{user_id}_{hashlib.md5(fact.encode()).hexdigest()}"
        self.collection.delete(ids=[doc_id])
