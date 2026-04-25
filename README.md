# memblob

Lightweight local memory for Claude Code. Extracts facts from conversations, stores them as vectors, and retrieves them semantically — all on-device via Ollama and ChromaDB.

Think of it as a minimal [mem0](https://github.com/mem0ai/mem0) that runs entirely on your machine with no cloud services.

## How it works

1. **Extract** — send text to a local LLM (`gemma4:e2b`) with a prompt that returns a JSON list of key facts
2. **Embed** — turn each fact into a vector using `nomic-embed-text` via Ollama
3. **Store** — persist the vector + text in ChromaDB (embedded, no server needed)
4. **Retrieve** — on new conversations, embed the query and return nearest-neighbour facts

Deduplication is cosine-distance based: facts within distance 0.08 of an existing memory are silently dropped.

## Requirements

- [Ollama](https://ollama.com) running locally
- The following models pulled:

```bash
ollama pull gemma4:e2b
ollama pull nomic-embed-text
```

- Python 3.9+

## Installation

```bash
git clone <repo-url> memblob
cd memblob
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Register with Claude Code

```bash
claude mcp add --scope user memblob \
  /path/to/memblob/.venv/bin/python \
  /path/to/memblob/server.py
```

Replace `/path/to/memblob` with your actual clone path. The `--scope user` flag makes it available across all projects, not just the current one.

Verify it's live by running `/mcp` in a Claude Code session — `memblob` should appear with four tools.

## MCP tools

| Tool | Description |
|---|---|
| `add_memory(text, user_id?)` | Extract facts from text and store them |
| `search_memory(query, user_id?, n?)` | Return the `n` most relevant memories for a query |
| `list_memories(user_id?)` | Dump all stored memories for a user |
| `delete_memory(fact, user_id?)` | Remove a specific memory by exact text |

`user_id` defaults to `"default"` — useful if you want separate memory namespaces.

## Usage example

In a Claude Code session:

```
add_memory("I prefer concise responses. I use Claude Code daily on a MacBook Air M2.")
→ Stored 2 memories:
  - Prefers concise responses
  - Uses Claude Code daily on a MacBook Air M2

search_memory("what machine does the user work on?")
→ Uses Claude Code daily on a MacBook Air M2
```

## Memory storage

Facts are persisted in `./memory_db/` (a ChromaDB SQLite store) relative to the `server.py` directory. Back it up or move it freely — it's just a folder.

## Compared to mem0

| Feature | memblob | mem0 |
|---|---|---|
| Fully local | yes | optional |
| Fact extraction | yes | yes |
| Semantic dedup | near-verbatim only | LLM-based (catches paraphrases) |
| Conflict resolution | accumulates | updates/merges |
| Memory decay/scoring | no | yes |
| Entity graph | no | yes |
| Setup | ~5 min | more |

## Changing models

Edit the two constants at the top of `memory.py`:

```python
EMBED_MODEL = "nomic-embed-text"   # any Ollama embedding model
EXTRACT_MODEL = "gemma4:e2b"       # any Ollama chat model
```

Any model available via `ollama list` works. Smaller models (`llama3.2:3b`, `qwen2.5:3b`) are faster; larger ones extract more accurately.
