"""One-shot: re-extract and consolidate existing memories into richer tagged entries.

Run from the venv:
    .venv/bin/python consolidate.py            # dry-run, prints proposed result
    .venv/bin/python consolidate.py --apply    # wipe & rewrite after confirmation
    .venv/bin/python consolidate.py --apply --user-id <id>

Default user_id is "default" (matches list.py / SimpleMemory defaults).
"""
import argparse
import hashlib
import json
import sys

from memory import EXTRACT_PROMPT, APIMemory, LocalMemory, create_memory


def llm_consolidate(mem, joined_text: str) -> list[str]:
    """Call the same chat model the backend uses, with the new EXTRACT_PROMPT."""
    prompt = EXTRACT_PROMPT.format(text=joined_text)
    if isinstance(mem, APIMemory):
        resp = mem._client.chat.completions.create(
            model=mem._chat_model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content.strip()
    elif isinstance(mem, LocalMemory):
        resp = mem._ollama.chat(
            model=mem._extract_model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp["message"]["content"].strip()
    else:
        raise RuntimeError(f"Unknown memory backend: {type(mem).__name__}")

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="wipe existing rows and store the consolidated set")
    ap.add_argument("--user-id", default="default")
    args = ap.parse_args()

    mem = create_memory()
    existing = mem.list_all(user_id=args.user_id)
    if not existing:
        print(f"No memories for user_id={args.user_id!r}. Nothing to do.")
        return

    print(f"--- {len(existing)} existing entries for user_id={args.user_id!r} ---")
    for f in existing:
        print(f"  - {f}")

    # Frame the existing fragments as a conversation so the prompt's "Conversation:" framing fits.
    joined = "The user has previously shared the following facts about themselves:\n" + "\n".join(
        f"- {f}" for f in existing
    )
    print("\n--- Asking model to consolidate... ---")
    new_facts = llm_consolidate(mem, joined)

    print(f"\n--- {len(new_facts)} proposed consolidated entries ---")
    for f in new_facts:
        print(f"  + {f}")

    if not args.apply:
        print("\n(dry-run) Re-run with --apply to wipe the old rows and store these.")
        return

    confirm = input(f"\nWipe {len(existing)} old rows and store {len(new_facts)} new ones? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(1)

    # Delete by reconstructing the deterministic ids used in _store_facts.
    old_ids = [f"{args.user_id}_{hashlib.md5(f.encode()).hexdigest()}" for f in existing]
    mem.collection.delete(ids=old_ids)
    print(f"Deleted {len(old_ids)} old rows.")

    stored = mem._store_facts(new_facts, user_id=args.user_id)
    print(f"Stored {len(stored)} new rows:")
    for f in stored:
        print(f"  + {f}")


if __name__ == "__main__":
    main()
