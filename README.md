# Institutional Memory Agent — Card A: New-Hire Onboarding

Basecamp capstone: **Track 02 — Institutional Memory Agent**

An agent that helps new engineering hires navigate the company — policies, access, tooling, team contacts. Built on Anthropic's **Managed Agents API** (`client.beta.agents`, `client.beta.sessions`, `client.beta.memory_stores`). Memory persists in a cloud-hosted store across every session, and the agent reconciles contradictions when policies change.

---

## How it works

```
create_agent.py         ← provisions agent + environment + memory store (once)
run_session_1.py        ← round1 docs → baseline answer → writes to /mnt/memory/
run_session_2.py        ← round2 docs → updated answer → reconciles contradictions
inspect_memory.py       ← shows what the agent stored (run between sessions)
```

The same question is asked in both sessions. **The demo is the diff:**

```bash
diff outputs/session1.txt outputs/session2.txt
```

Session 1 cites the old prod-access workflow (Slack + SRE pairing session). Session 2 leads with "⚠️ This changed" and gives the new process (IAM portal, no pairing session required).

---

## Scenario — Card A: New-Hire Onboarding Agent

**Test question (identical in both sessions):**
> "I just joined the company and I need read-only prod access to debug an issue tomorrow. What do I do? Be specific about the steps and the people I need to talk to."

**What "better answer in session 2" looks like:**
- Leads with the policy change (⚠️ banner)
- Cites the new IAM portal flow, not the old #sre-access-requests Slack channel
- Notes the tenure requirement dropped from 2 weeks to 3 working days
- Names the updated team directory entry (re-org: one person moved teams)

---

## Synthetic documents

### Round 1 (initial onboarding docs)
| File | Contents |
|------|----------|
| `synthetic-data/round1/onboarding-handbook.md` | General onboarding guide, tooling, git workflow |
| `synthetic-data/round1/team-directory.md` | Team structure, who owns what, contacts |
| `synthetic-data/round1/access-policy.md` | Production access policy (January 2026) |

### Round 2 (policy update + re-org)
| File | Contents |
|------|----------|
| `synthetic-data/round2/policy-update-2026-05-15.md` | New prod-access policy — eliminates SRE pairing, uses IAM + online cert |
| `synthetic-data/round2/team-directory-update.md` | Updated directory after re-org |

---

## Requirements

```
anthropic>=1.5.0
```

Install:
```bash
pip install -r requirements.txt
```

---

## Setup

```bash
export ANTHROPIC_API_KEY="sk-ant-..."

# 1. Provision the agent (once)
python create_agent.py

# 2. Run Session 1 — baseline answer
python run_session_1.py

# 3. Inspect memory
python inspect_memory.py

# 4. Run Session 2 — reconciled answer
python run_session_2.py

# 5. See the diff
diff outputs/session1.txt outputs/session2.txt
```

---

## What Managed Agents gives you

| Capability | How it's used |
|-----------|---------------|
| `client.beta.agents.create()` | Provisions the onboarding agent with system prompt |
| `client.beta.environments.create()` | Cloud-hosted session container |
| `client.beta.memory_stores.create()` | Persistent `/mnt/memory/` across sessions |
| `client.beta.sessions.create()` | Fresh session per run (same memory store) |
| `client.beta.sessions.events.stream()` | Streams agent output + tool calls live |

The agent's memory **lives in the cloud** — it persists between script runs, between team members' laptops, between sessions. No local filesystem, no database.

---

## Other scenario cards

See `scenario-cards.md` for Card B (Customer Success), Card C (M&A Diligence), and Card D (Sales Engineer). Round1/round2 docs can be lightly adapted for any card.

---

## Credits

Built from [`ksn0ky/institutional-memory`](https://github.com/ksn0ky/institutional-memory) — adapted for Card A by the Basecamp team.
