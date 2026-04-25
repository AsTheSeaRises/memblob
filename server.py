import sys
import os

# Ensure imports resolve when launched by Claude Code from any working directory
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP
from memory import SimpleMemory

DB_PATH = os.path.expanduser("~/.memblob/memory_db")

mcp = FastMCP("memblob")
mem = SimpleMemory(db_path=DB_PATH)


@mcp.tool()
def add_memory(text: str, user_id: str = "default") -> str:
    """Extract and store facts from a conversation or text snippet."""
    facts = mem.add(text, user_id)
    if not facts:
        return "No new facts extracted (all duplicates or JSON parse error)."
    return f"Stored {len(facts)} memories:\n" + "\n".join(f"- {f}" for f in facts)


@mcp.tool()
def search_memory(query: str, user_id: str = "default", n: int = 5) -> str:
    """Retrieve the most relevant memories for a query."""
    results = mem.search(query, user_id, n)
    return "\n".join(results) if results else "No memories found."


@mcp.tool()
def list_memories(user_id: str = "default") -> str:
    """List all stored memories for a user."""
    results = mem.list_all(user_id)
    return "\n".join(results) if results else "No memories stored."


@mcp.tool()
def delete_memory(fact: str, user_id: str = "default") -> str:
    """Delete a specific memory by its exact text."""
    mem.delete(fact, user_id)
    return f"Deleted: {fact}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
