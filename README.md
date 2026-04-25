# memblob

Lightweight local memory for Claude Code. Extracts facts from conversations, stores them as vectors, and retrieves them semantically — all on-device via Ollama and ChromaDB.

Think of it as a minimal [mem0](https://github.com/mem0ai/mem0) that runs entirely on your machine with no cloud services.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Claude Desktop / Claude Code            │
│                                                     │
│  add_memory()   search_memory()   list_memories()   │
└────────────────────────┬────────────────────────────┘
                         │ MCP stdio
                         ▼
┌─────────────────────────────────────────────────────┐
│                 server.py (FastMCP)                  │
│                "memblob" MCP server                  │
└──────────┬──────────────────────────┬───────────────┘
           │                          │
           ▼                          ▼
┌──────────────────┐      ┌───────────────────────────┐
│     Ollama       │      │        ChromaDB            │
│                  │      │  (embedded, local SQLite)  │
│  gemma4:e2b      │      │                            │
│  → fact extract  │      │  cosine similarity index   │
│                  │      │  ./memory_db/              │
│  nomic-embed-    │      │                            │
│  text            │      │  stores: fact text         │
│  → embeddings    │      │          vector            │
└──────────────────┘      │          user_id           │
                          └───────────────────────────┘
```

Every `add_memory` call goes left (Ollama extracts facts + embeds them) then right (ChromaDB stores them). Every `search_memory` goes right only — Ollama embeds the query, ChromaDB finds nearest neighbours.

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

## Triggering memory automatically

By default the tools are passive — Claude only uses them when you explicitly ask ("remember this", "what do you know about me?").

To make it always-on, add the following prompt wherever Claude reads its instructions. There are three scopes depending on which client you're using:

**Prompt to add:**
```
At the start of every conversation, call search_memory with a query
relevant to what the user is asking, and include the results as context.

When the user shares personal facts, preferences, tools they use, or
decisions they've made, call add_memory to store them.
```

**Where to put it:**

| Scope | Location | Applies to |
|---|---|---|
| Claude Code — all projects | `~/.claude/CLAUDE.md` (create if missing) | Every Claude Code session globally |
| Claude Code — one project | `CLAUDE.md` in the project root | That project only |
| Claude Desktop | Settings → Custom Instructions | All Claude Desktop conversations |

The three modes, in order of how automatic they are:

| Mode | How triggered |
|---|---|
| Manual | Explicitly say "remember this" or "check your memory" |
| CLAUDE.md / Custom Instructions | Claude follows a standing instruction to use tools each session |
| Programmatic (future) | LAN HTTP API injects memories into every request automatically |

## Adding memories

**Via a Claude session** — just tell Claude to remember something and it calls `add_memory` for you:

```
add_memory("I prefer concise responses. I use Claude Code daily on a MacBook Air M2.")
→ Stored 2 memories:
  - Prefers concise responses
  - Uses Claude Code daily on a MacBook Air M2

search_memory("what machine does the user work on?")
→ Uses Claude Code daily on a MacBook Air M2
```

**Via the terminal** — useful for bulk imports or scripting:

```bash
cd /path/to/memblob
.venv/bin/python3 -c "
from memory import SimpleMemory
m = SimpleMemory()
m.add('I prefer concise responses. I use dbt and Databricks.')
print(m.list_all())
"
```

**Inspect what's stored** at any time:

```bash
cd /path/to/memblob
.venv/bin/python3 -c "
from memory import SimpleMemory
for fact in SimpleMemory().list_all():
    print('-', fact)
"
```

## Memory storage

Facts are persisted in `~/.memblob/memory_db/` — a fixed absolute path so Claude Code, Claude Desktop, and terminal scripts all read and write the same database. Back it up or move it freely — it's just a folder.

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

## Roadmap

- [ ] **LAN HTTP API** — FastAPI wrapper over `memory.py` so any LLM or tool on the local network can hit `/add`, `/search`, `/list`, `/delete` via plain HTTP, without needing an MCP client

## Changing models

Edit the two constants at the top of `memory.py`:

```python
EMBED_MODEL = "nomic-embed-text"   # any Ollama embedding model
EXTRACT_MODEL = "gemma4:e2b"       # any Ollama chat model
```

Any model available via `ollama list` works. Smaller models (`llama3.2:3b`, `qwen2.5:3b`) are faster; larger ones extract more accurately.
