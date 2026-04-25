"""Smoke test for the API backend (DashScope / any OpenAI-compatible provider).

Run: `.venv/bin/python test_api.py`
Requires: .env configured with MEMBLOB_BACKEND=api and API_KEY.
"""

import os
from memory import APIMemory


def main() -> None:
    chat_model = os.environ.get("API_CHAT_MODEL", "qwen-plus")
    embed_model = os.environ.get("API_EMBED_MODEL", "text-embedding-v4")

    mem = APIMemory()
    client = mem._client

    print(f"Testing chat model: {chat_model}")
    chat = client.chat.completions.create(
        model=chat_model,
        messages=[{"role": "user", "content": "Say 'hello from the API' and nothing else."}],
    )
    print(f"  → {chat.choices[0].message.content}")

    print(f"\nTesting embedding model: {embed_model}")
    emb = client.embeddings.create(model=embed_model, input=["test sentence"])
    vec = emb.data[0].embedding
    print(f"  → got vector of dimension {len(vec)}")

    print("\nAll good. API backend is reachable.")


if __name__ == "__main__":
    main()
