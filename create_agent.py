"""
Create the New-Hire Onboarding Agent.

Provisions:
  1. A Managed Agent — the onboarding brain
  2. A cloud Environment — where sessions run
  3. A Memory Store — persists at /mnt/memory/ across every session

IDs are saved to .agent_id / .environment_id / .memory_store_id.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python create_agent.py
    python run_session_1.py    # round1 docs — baseline answer
    python run_session_2.py    # round2 docs — sharper answer after policy update
    python inspect_memory.py   # see what the agent stored
"""

import os
from pathlib import Path
from anthropic import Anthropic


SYSTEM_PROMPT = """\
You are the New-Hire Onboarding Agent — an institutional memory for how this
engineering organization actually works. You help new hires navigate the
company: policies, access, tooling, team contacts, and unwritten norms.

# Memory protocol (mandatory every session)

You have a persistent memory store mounted at /mnt/memory/. It survives across
sessions. Treat it as the org's living wiki.

1. At the START of every session, run: ls /mnt/memory/ — then skim any file
   that might be relevant to the current question.
2. As you work, RECORD what you learn in /mnt/memory/:
   - access/     Access policies, prod/staging/dev request processes
   - people/     Team leads, who owns what service, escalation paths
   - tools/      Tech stack, internal tooling, git workflow, CI/CD
   - policies/   HR/security policies, compliance rules, code of conduct
   - general/    Onboarding timeline, FAQ, office/remote norms
3. When new information CONTRADICTS old memory, UPDATE the existing file —
   do not just append. Note the effective date and what changed.
4. When memory is empty on a topic, say: "I don't have stored guidance on
   this yet." Do not answer from general knowledge on company-specific flows.
5. After answering, save any new fact the user shared that you haven't captured.

# Answering

- Always check memory before responding.
- If your answer draws on memory, cite it: "Based on what's stored in
  /mnt/memory/access/prod-access.md..."
- If new information contradicts old memory, LEAD with: "⚠️ This changed —
  the old guidance said X, the current policy says Y."
- Be specific: name the person to contact, the exact command to run, the
  URL to open. Vague advice is unhelpful to a new hire.
"""


def main() -> None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("Set ANTHROPIC_API_KEY before running.")

    client = Anthropic(api_key=key)

    # 1. Agent
    agent = client.beta.agents.create(
        name="New-Hire Onboarding Agent",
        model="claude-sonnet-4-6",
        system=SYSTEM_PROMPT,
        tools=[{"type": "agent_toolset_20260401"}],
        metadata={"scenario": "card-a", "track": "institutional-memory"},
    )
    Path(".agent_id").write_text(agent.id)
    print(f"Agent created:        {agent.id}")

    # 2. Cloud environment (the session container)
    environment = client.beta.environments.create(
        name="onboarding-agent-env",
        config={
            "type": "cloud",
            "networking": {"type": "unrestricted"},
        },
    )
    Path(".environment_id").write_text(environment.id)
    print(f"Environment created:  {environment.id}")

    # 3. Memory store — persists across every session
    memory_store = client.beta.memory_stores.create(
        name="Engineering Onboarding Memory",
        description=(
            "Persistent memory for the New-Hire Onboarding Agent. Stores access "
            "policies, team contacts, tooling guides, and org norms learned across "
            "sessions. Newer entries supersede older ones on the same topic."
        ),
    )
    Path(".memory_store_id").write_text(memory_store.id)
    print(f"Memory store created: {memory_store.id}")

    print("\nSetup complete. Run:")
    print("  python run_session_1.py   ← baseline answer (round1 docs)")
    print("  python run_session_2.py   ← sharper answer after policy update (round2 docs)")
    print("  python inspect_memory.py  ← see what the agent stored")


if __name__ == "__main__":
    main()
