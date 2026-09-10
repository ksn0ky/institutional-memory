"""
Session 2 — Same agent, same memory store, updated policy docs.

Round 2 documents contradict round 1 in two ways:
  - prod-access workflow changed (new policy, different approver)
  - team directory updated after a re-org (one person moved teams)

The agent should:
  - Read /mnt/memory/ first (what it learned in Session 1)
  - Notice the contradictions in round 2 docs
  - UPDATE memory (not just append)
  - Answer the SAME question — citing the new policy, not the old workflow

Usage:
    python run_session_2.py
    diff outputs/session1.txt outputs/session2.txt   ← the demo moment
    python inspect_memory.py   ← see memory was UPDATED not just appended
"""

import os
from pathlib import Path
from anthropic import Anthropic


# Identical question — so the diff is meaningful
TEST_QUESTION = (
    "I just joined the company and I need read-only prod access to debug an "
    "issue tomorrow. What do I do? Be specific about the steps and the people "
    "I need to talk to."
)

DOCS_DIR = Path("synthetic-data/round2")
OUTPUT_DIR = Path("outputs")


def load_docs(docs_dir: Path) -> str:
    blocks = []
    for path in sorted(docs_dir.glob("*.md")):
        print(f"  including: {path.name}")
        blocks.append(f"===== DOCUMENT: {path.name} =====\n{path.read_text()}")
    return "\n\n".join(blocks)


def main() -> None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("Set ANTHROPIC_API_KEY before running.")

    for f in (".agent_id", ".environment_id", ".memory_store_id"):
        if not Path(f).exists():
            raise SystemExit(f"Missing {f} — run create_agent.py first.")

    agent_id        = Path(".agent_id").read_text().strip()
    environment_id  = Path(".environment_id").read_text().strip()
    memory_store_id = Path(".memory_store_id").read_text().strip()

    client = Anthropic(api_key=key)

    print(f"Loading docs from {DOCS_DIR}/...")
    context = load_docs(DOCS_DIR)

    print(f"\nStarting Session 2 — fresh session, same memory store ({memory_store_id})...")
    session = client.beta.sessions.create(
        agent=agent_id,
        environment_id=environment_id,
        title="Session 2 — policy update + re-org",
        resources=[{
            "type": "memory_store",
            "memory_store_id": memory_store_id,
            "access": "read_write",
            "instructions": (
                "This is your persistent onboarding memory from Session 1. "
                "Some entries may be out of date — the new documents in this "
                "session contradict them. UPDATE existing files rather than "
                "appending. Note what changed and the effective date."
            ),
        }],
    )

    user_message = (
        "Some of our policies and team structure changed recently. "
        "I'm sharing updated documents below — some contradict what you "
        "recorded in Session 1.\n\n"
        "Please:\n"
        "1. Check /mnt/memory/ — load what you know from Session 1.\n"
        "2. Read the new documents carefully.\n"
        "3. For anything that contradicts Session 1 memory: UPDATE the file, "
        "   note the effective date and what changed.\n"
        "4. Answer the question at the bottom.\n"
        "5. If your answer differs from Session 1, LEAD with: "
        "   '⚠️ This changed — the old guidance said X, the new policy says Y.'\n\n"
        f"{context}\n\n"
        "=" * 60 + "\n"
        f"QUESTION: {TEST_QUESTION}"
    )

    text_parts: list[str] = []
    print("\n--- Agent working (memory updates shown) ---\n")

    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(
            session.id,
            events=[{
                "type": "user.message",
                "content": [{"type": "text", "text": user_message}],
            }],
        )
        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if getattr(block, "type", None) == "text":
                        text_parts.append(block.text)
                        print(block.text, end="", flush=True)
            elif event.type == "agent.tool_use":
                name   = getattr(event, "name", "?")
                inp    = getattr(event, "input", {}) or {}
                target = inp.get("path") or inp.get("file_path") or inp.get("command") or ""
                marker = "📝 memory" if "/mnt/memory" in str(target) else "  tool"
                print(f"\n  [{marker}: {name}  {str(target)[:60]}]", flush=True)
            elif event.type == "session.status_idle":
                print("\n\n[session complete]")
                break

    OUTPUT_DIR.mkdir(exist_ok=True)
    answer = "".join(text_parts)
    out = OUTPUT_DIR / "session2.txt"
    out.write_text(
        f"=== SESSION 2 — After Policy Update + Re-org ===\n"
        f"Question: {TEST_QUESTION}\n\n"
        f"--- ANSWER ---\n{answer}\n"
    )
    print(f"\nSaved → {out}")
    print()
    print("The demo moment:")
    print("  diff outputs/session1.txt outputs/session2.txt")
    print()
    print("What to look for:")
    print("  - Session 2 leads with '⚠️ This changed'")
    print("  - Cites the new prod-access policy, not the old workflow")
    print("  - Names the updated approver from the re-org")
    print()
    print("  python inspect_memory.py  ← confirm memory was updated, not just appended")


if __name__ == "__main__":
    main()
