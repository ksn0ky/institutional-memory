"""
Session 1 — Baseline ingestion.

Feeds the agent the initial onboarding documents (round1):
  - onboarding-handbook.md
  - team-directory.md
  - access-policy.md

The agent reads them, answers the test question, and writes key facts to
/mnt/memory/ — which persists for Session 2.

After this runs, compare with Session 2 to see the agent get sharper.

Usage:
    python run_session_1.py
    python inspect_memory.py   ← see what the agent stored
    python run_session_2.py    ← add policy updates and re-run
"""

import os
from pathlib import Path
from anthropic import Anthropic


# Same question asked in both sessions — so you can diff the answers
TEST_QUESTION = (
    "I just joined the company and I need read-only prod access to debug an "
    "issue tomorrow. What do I do? Be specific about the steps and the people "
    "I need to talk to."
)

DOCS_DIR = Path("synthetic-data/round1")
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

    print(f"\nStarting Session 1 (memory store: {memory_store_id})...")
    session = client.beta.sessions.create(
        agent=agent_id,
        environment_id=environment_id,
        title="Session 1 — baseline onboarding docs",
        resources=[{
            "type": "memory_store",
            "memory_store_id": memory_store_id,
            "access": "read_write",
            "instructions": (
                "This is your persistent onboarding memory. Mounted at /mnt/memory/. "
                "Check it at the start. After reading the documents, save key facts "
                "to /mnt/memory/<category>/ so future sessions are sharper."
            ),
        }],
    )

    user_message = (
        "I'm giving you our company's onboarding documents. Please:\n\n"
        "1. Check /mnt/memory/ to see what you already know.\n"
        "2. Read the documents below carefully.\n"
        "3. Answer the question at the bottom.\n"
        "4. Before finishing, save key facts to /mnt/memory/ organized by "
        "   category (access/, people/, tools/, policies/, general/).\n\n"
        f"{context}\n\n"
        "=" * 60 + "\n"
        f"QUESTION: {TEST_QUESTION}"
    )

    text_parts: list[str] = []
    print("\n--- Agent working (memory writes shown) ---\n")

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
    out = OUTPUT_DIR / "session1.txt"
    out.write_text(
        f"=== SESSION 1 — Baseline ===\n"
        f"Question: {TEST_QUESTION}\n\n"
        f"--- ANSWER ---\n{answer}\n"
    )
    print(f"\nSaved → {out}")
    print("Next:  python inspect_memory.py   ← see what was stored")
    print("Then:  python run_session_2.py    ← run with updated policy docs")


if __name__ == "__main__":
    main()
