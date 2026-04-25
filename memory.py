import os
import hashlib
import json

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from dotenv import load_dotenv

# Load .env from the directory of this file, regardless of cwd
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

EXTRACT_PROMPT = """Extract key facts from this conversation as a JSON array of short statements.
Only extract concrete, factual information worth remembering long-term (names, preferences, tools, decisions).
Return ONLY a JSON array of strings with no markdown or explanation.

Conversation:
{text}"""

DEFAULT_DB_PATH = os.path.expanduser("~/.memblob/memory_db")
DEDUP_DISTANCE = 0.08  # cosine distance; facts closer than this are treated as duplicates


# ---------------------------------------------------------------------------
# Shared ChromaDB logic
# ---------------------------------------------------------------------------

class _BaseMemory:
    def __init__(self, db_path: str, ef: EmbeddingFunction):
        self.chroma = chromadb.PersistentClient(path=db_path)
        self.collection = self.chroma.get_or_create_collection(
            "memories",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, text: str, user_id: str = "default") -> list[str]:
        raise NotImplementedError

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

    def _store_facts(self, facts: list, user_id: str) -> list[str]:
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


# ---------------------------------------------------------------------------
# Local backend — fully on-device via Ollama
# ---------------------------------------------------------------------------

class LocalMemory(_BaseMemory):
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        from chromadb.utils.embedding_functions.ollama_embedding_function import OllamaEmbeddingFunction
        import ollama as _ollama
        self._ollama = _ollama
        self._extract_model = os.environ.get("OLLAMA_EXTRACT_MODEL", "gemma4:e2b")
        ef = OllamaEmbeddingFunction(
            url="http://localhost:11434/api/embeddings",
            model_name=os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        )
        super().__init__(db_path, ef)

    def add(self, text: str, user_id: str = "default") -> list[str]:
        resp = self._ollama.chat(
            model=self._extract_model,
            messages=[{"role": "user", "content": EXTRACT_PROMPT.format(text=text)}],
        )
        raw = resp["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            facts = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return self._store_facts(facts, user_id)


# ---------------------------------------------------------------------------
# API backend — any OpenAI-compatible provider
# ---------------------------------------------------------------------------

class _APIEmbeddingFunction(EmbeddingFunction):
    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    def __call__(self, input: Documents) -> Embeddings:
        items = list(input)
        embeddings: Embeddings = []
        for i in range(0, len(items), 10):
            resp = self._client.embeddings.create(model=self._model, input=items[i:i + 10])
            embeddings.extend(d.embedding for d in resp.data)
        return embeddings


class APIMemory(_BaseMemory):
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        from openai import OpenAI
        api_key = os.environ.get("API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            raise EnvironmentError("API_KEY (or DASHSCOPE_API_KEY) must be set for the api backend.")
        base_url = os.environ.get("API_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
        self._chat_model = os.environ.get("API_CHAT_MODEL", "qwen-plus")
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        ef = _APIEmbeddingFunction(
            client=self._client,
            model=os.environ.get("API_EMBED_MODEL", "text-embedding-v4"),
        )
        super().__init__(db_path, ef)

    def add(self, text: str, user_id: str = "default") -> list[str]:
        resp = self._client.chat.completions.create(
            model=self._chat_model,
            messages=[{"role": "user", "content": EXTRACT_PROMPT.format(text=text)}],
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            facts = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return self._store_facts(facts, user_id)


# ---------------------------------------------------------------------------
# Factory — reads MEMBLOB_BACKEND from env, defaults to 'api'
# ---------------------------------------------------------------------------

def create_memory(db_path: str = DEFAULT_DB_PATH) -> _BaseMemory:
    backend = os.environ.get("MEMBLOB_BACKEND", "api").lower()
    if backend == "local":
        return LocalMemory(db_path)
    return APIMemory(db_path)


SimpleMemory = create_memory  # server.py calls SimpleMemory(db_path=...) — unchanged
