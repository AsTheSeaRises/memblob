# memblob

Lightweight local memory for Claude Code and Claude Desktop. Extracts facts from conversations, stores them as vectors, and retrieves them semantically. Vectors and the database live on-device in ChromaDB. Two backends are supported — fully local via Ollama, or via any OpenAI-compatible API provider.

## Backends

| Backend | Extraction | Embeddings | Requires |
|---|---|---|---|
| `local` | Ollama (on-device LLM) | Ollama (on-device) | Ollama running + models pulled |
| `api` | Any OpenAI-compatible API | Same API | API key + endpoint |

Switch backends by setting `MEMBLOB_BACKEND=local` or `MEMBLOB_BACKEND=api` in your `.env` file. DashScope (Qwen) is the documented API example, but any OpenAI-compatible provider works.

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
│  Ollama (local)  │      │        ChromaDB            │
│  — OR —          │      │  (embedded, local SQLite)  │
│  API provider    │      │                            │
│                  │      │  cosine similarity index   │
│  → fact extract  │      │  ~/.memblob/memory_db/     │
│  → embeddings    │      │                            │
└──────────────────┘      │  stores: fact text         │
                          │          vector            │
                          │          user_id           │
                          └───────────────────────────┘
```

## How it works

1. **Extract** — send text to an LLM with a prompt that returns a JSON list of key facts
2. **Embed** — turn each fact into a vector using an embedding model
3. **Store** — persist the vector + text in ChromaDB (embedded, no server needed)
4. **Retrieve** — on new conversations, embed the query and return nearest-neighbour facts

Deduplication is cosine-distance based: facts within distance 0.08 of an existing memory are silently dropped.

## Requirements

- Python 3.9+
- **`local` backend**: [Ollama](https://ollama.com) running locally with models pulled (see below)
- **`api` backend**: API key for an OpenAI-compatible provider (DashScope example below)

## Installation

```bash
git clone <repo-url> memblob
cd memblob
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# edit .env — set MEMBLOB_BACKEND and fill in the relevant section
```

The server loads `.env` automatically at startup — no need to export variables in your shell or pass `--env` flags to `claude mcp add`.

### Local backend setup

```bash
# Pull the required Ollama models
ollama pull gemma4:e2b
ollama pull nomic-embed-text
```

In `.env`:
```
MEMBLOB_BACKEND=local
```

### API backend setup (DashScope / Qwen example)

Get an API key from the [Alibaba Cloud Model Studio console](https://bailian.console.alibabacloud.com/) (international).

In `.env`:
```
MEMBLOB_BACKEND=api
API_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
API_CHAT_MODEL=qwen-plus
API_EMBED_MODEL=text-embedding-v4
API_KEY=sk-your-key-here
```

Any OpenAI-compatible provider works — change `API_BASE_URL`, `API_CHAT_MODEL`, `API_EMBED_MODEL`, and `API_KEY` to match.

## Register with Claude Code

```bash
claude mcp add --scope user memblob \
  -- /path/to/memblob/.venv/bin/python /path/to/memblob/server.py
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

## Roadmap

- [ ] **LAN HTTP API** — FastAPI wrapper over `memory.py` so any LLM or tool on the local network can hit `/add`, `/search`, `/list`, `/delete` via plain HTTP, without needing an MCP client

- [ ] **MCP stats proxy** — a lightweight MCP proxy (`memblob_proxy.py`) that sits between any Claude client and the real memblob server. Exposes the same four tools so Claude can't tell the difference, but logs every call (operation, query, result count, timestamp) to SQLite before forwarding. Enables a watch CLI to monitor memory usage in real time. ~60-80 lines of Python. Architecture:

  ```
  Claude (any client)
       │ MCP
       ▼
  memblob_proxy.py  ←── logs to SQLite
       │ forwards call unchanged
       ▼
  server.py (real memblob)
       │
       ▼
  ChromaDB + DashScope
  ```

## Switching backends

The two backends use different embedding models with incompatible vector spaces, so switching requires re-embedding your stored memories. Update `.env` to the new backend, then either:

- **Wipe and start fresh:** `rm -rf ~/.memblob/memory_db`
- **Preserve existing memories:** `.venv/bin/python migrate.py` — re-embeds all stored facts with the new backend, no re-extraction needed.

## Changing models

All models are configurable in `.env` — no code changes needed:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_EXTRACT_MODEL` | `gemma4:e2b` | Ollama chat model for extraction |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `API_CHAT_MODEL` | `qwen-plus` | API chat model for extraction |
| `API_EMBED_MODEL` | `text-embedding-v4` | API embedding model |
