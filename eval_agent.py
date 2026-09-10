"""The Eval Agent — scores the onboarding agent's answers against a rubric.

Two layers, deliberately:

1. A deterministic pass (regex over the transcript). Free, instant, and it
   cannot flatter the agent. Good at catching a missing keyword; useless at
   judging whether "you'll need to wait a few days first" counts as stating the
   3-working-day tenure rule.
2. An LLM judge. Reads each criterion's question and scores 0-2 with a reason.
   Catches paraphrase, and — critically — judges the negative criteria, where
   "mentions the old Slack channel" and "prescribes the old Slack channel" look
   identical to a regex but are opposite behaviours.

The judge is the authoritative score. The deterministic pass runs alongside it
so that a disagreement is visible in the report rather than silently averaged
away: a criterion the regex finds and the judge rejects is usually the agent
name-dropping the right term in the wrong context.

The judge is a plain Messages-API call, not a Managed Agent. Judging needs no
filesystem, no memory store and no container, and keeping it stateless means
every run scores from the transcript alone.

Usage:
    python eval_agent.py                 # score whatever is in outputs/
    python eval_agent.py --offline       # deterministic layer only, no API spend
    python eval_agent.py --session 2     # score one session
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

import eval_rubric
from eval_rubric import Criterion

JUDGE_MODEL = "claude-sonnet-5"
OUTPUT_DIR = Path("outputs")
REPORT_PATH = OUTPUT_DIR / "eval-report.md"

TRANSCRIPTS = {
    "session1": OUTPUT_DIR / "session1.txt",
    "session2": OUTPUT_DIR / "session2.txt",
}

JUDGE_SYSTEM_PROMPT = """\
You are the Eval Agent. You score a New-Hire Onboarding Agent's answers against
a fixed rubric. You are not helping the engineer; you are grading the answer.

Scoring scale, applied per criterion:
  2 — fully satisfied. The answer does this clearly and correctly.
  1 — partially satisfied. Gestures at it, or gets it right but vaguely.
  0 — not satisfied, or actively wrong.

Rules:
- Score ONLY against the criterion's question. Do not reward an answer for
  being well written, well organised, or confident.
- Negative criteria ("does the answer AVOID X") score 2 when the answer stays
  clean and 0 when it commits the error. Mentioning an outdated process purely
  to contrast it with the current one is not committing the error.
- A confident, fluent answer that states the wrong policy scores 0. Fluency is
  not evidence.
- Quote the specific phrase you scored on. If you cannot quote it, the answer
  probably does not contain it, and the score is 0.

Return ONLY a JSON array, no prose around it:
[{"id": "<criterion id>", "score": 0|1|2, "quote": "<short quote or empty>", "reason": "<one sentence>"}]
"""


def load_answer(path: Path) -> str:
    """Pull the answer body out of a session transcript."""
    text = path.read_text()
    marker = "--- ANSWER ---"
    return text.split(marker, 1)[1].strip() if marker in text else text.strip()


def deterministic_scores(answer: str, criteria: list[Criterion]) -> dict:
    """Regex layer. Reports signal, never a final score."""
    results = {}
    haystack = answer.lower()
    for c in criteria:
        matched = [p for p in c.must_match if re.search(p, haystack, re.I)]
        forbidden = [p for p in c.must_not_match if re.search(p, haystack, re.I)]
        if not c.must_match and not c.must_not_match:
            verdict = "n/a"          # judge-only criterion
        elif forbidden:
            verdict = "fail"
        elif c.must_match and not matched:
            verdict = "fail"
        else:
            verdict = "pass"
        results[c.id] = {
            "verdict": verdict,
            "matched": matched,
            "forbidden_hits": forbidden,
        }
    return results


def build_judge_prompt(question: str, answer: str, criteria: list[Criterion]) -> str:
    lines = [
        "The onboarding agent was asked:",
        "",
        question,
        "",
        "It answered:",
        "",
        "<answer>",
        answer,
        "</answer>",
        "",
        "Score the answer against each criterion below.",
        "",
    ]
    for c in criteria:
        lines.append(f'- id: {c.id}')
        lines.append(f'  question: {c.judge_question}')
        lines.append("")
    return "\n".join(lines)


def parse_judge_json(raw: str) -> list[dict]:
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        raise ValueError(f"judge did not return JSON:\n{raw[:500]}")
    return json.loads(match.group(0))


def judge(client, question: str, answer: str, criteria: list[Criterion]) -> dict:
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=4000,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_judge_prompt(question, answer, criteria)}],
    )
    raw = "".join(block.text for block in response.content if block.type == "text")
    scored = {item["id"]: item for item in parse_judge_json(raw)}

    missing = [c.id for c in criteria if c.id not in scored]
    if missing:
        raise ValueError(f"judge skipped criteria: {', '.join(missing)}")
    return scored


def score_control(client, offline: bool) -> dict | None:
    """Negative control: grade Session 1's answer with the Session 2 rubric.

    Session 1 predates the policy change, so it *should* fail the Session 2
    criteria badly. If it scores well, the rubric is measuring fluency rather
    than whether memory was actually updated, and the Session 2 result means
    nothing. Every eval needs a case it is known to fail.
    """
    path = TRANSCRIPTS["session1"]
    if not path.exists():
        print("  control: no session1 transcript — skipping")
        return None

    criteria = eval_rubric.for_session("session2")
    answer = load_answer(path)
    determ = deterministic_scores(answer, criteria)
    judged = {} if offline else judge(client, eval_rubric.TEST_QUESTION, answer, criteria)

    rows = []
    earned = possible = 0
    for c in criteria:
        j = judged.get(c.id)
        score = j["score"] if j else None
        if score is not None:
            earned += score * c.weight
            possible += 2 * c.weight
        rows.append({
            "criterion": c,
            "deterministic": determ[c.id],
            "score": score,
            "quote": (j or {}).get("quote", ""),
            "reason": (j or {}).get("reason", ""),
        })

    return {
        "session": "control (session1 answer vs session2 rubric)",
        "answer_chars": len(answer),
        "rows": rows,
        "earned": earned,
        "possible": possible,
        "pct": round(100 * earned / possible, 1) if possible else None,
    }


def score_session(session: str, client, offline: bool) -> dict | None:
    path = TRANSCRIPTS[session]
    if not path.exists():
        print(f"  {session}: no transcript at {path} — skipping")
        return None

    criteria = eval_rubric.for_session(session)
    answer = load_answer(path)
    determ = deterministic_scores(answer, criteria)
    judged = {} if offline else judge(client, eval_rubric.TEST_QUESTION, answer, criteria)

    rows = []
    earned = possible = 0
    for c in criteria:
        j = judged.get(c.id)
        score = j["score"] if j else None
        if score is not None:
            earned += score * c.weight
            possible += 2 * c.weight
        rows.append({
            "criterion": c,
            "deterministic": determ[c.id],
            "score": score,
            "quote": (j or {}).get("quote", ""),
            "reason": (j or {}).get("reason", ""),
        })

    return {
        "session": session,
        "answer_chars": len(answer),
        "rows": rows,
        "earned": earned,
        "possible": possible,
        "pct": round(100 * earned / possible, 1) if possible else None,
    }


def render_report(results: list[dict], offline: bool) -> str:
    out = ["# Onboarding Agent — Eval Report", ""]
    if offline:
        out += ["_Deterministic layer only (`--offline`); no judge scores._", ""]

    out += ["## Summary", "", "| Session | Score | % |", "| --- | --- | --- |"]
    for r in results:
        score = "—" if r["pct"] is None else f'{r["earned"]}/{r["possible"]}'
        pct = "—" if r["pct"] is None else f'{r["pct"]}%'
        out.append(f'| {r["session"]} | {score} | {pct} |')
    out.append("")

    for r in results:
        out += [f'## {r["session"]}', "", "| Criterion | W | Regex | Score | Why |", "| --- | --- | --- | --- | --- |"]
        for row in r["rows"]:
            c = row["criterion"]
            flag = " *(bonus)*" if c.bonus else ""
            score = "—" if row["score"] is None else str(row["score"])
            reason = row["reason"].replace("|", "\\|")
            out.append(
                f'| {c.summary}{flag} | {c.weight} | {row["deterministic"]["verdict"]} '
                f'| {score} | {reason} |'
            )
        out.append("")

        disagreements = [
            row for row in r["rows"]
            if row["score"] is not None
            and row["deterministic"]["verdict"] != "n/a"
            and ((row["deterministic"]["verdict"] == "pass") != (row["score"] == 2))
        ]
        if disagreements:
            out += ["**Regex/judge disagreements** — usually the right term used the wrong way:", ""]
            for row in disagreements:
                out.append(
                    f'- `{row["criterion"].id}`: regex {row["deterministic"]["verdict"]}, '
                    f'judge {row["score"]}/2 — {row["reason"]}'
                )
            out.append("")

    return "\n".join(out)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Score the onboarding agent against the rubric.")
    parser.add_argument("--offline", action="store_true", help="deterministic layer only, no API calls")
    parser.add_argument("--session", choices=["1", "2"], help="score only this session")
    parser.add_argument(
        "--control",
        action="store_true",
        help="negative control: score Session 1's answer against the Session 2 rubric",
    )
    args = parser.parse_args()

    sessions = [f"session{args.session}"] if args.session else list(TRANSCRIPTS)

    client = None
    if not args.offline:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit("Set ANTHROPIC_API_KEY (or use --offline).")
        client = Anthropic(api_key=key)

    print(f"Scoring {', '.join(sessions)}" + (" (offline)" if args.offline else f" with {JUDGE_MODEL}"))
    results = [r for r in (score_session(s, client, args.offline) for s in sessions) if r]
    if args.control:
        control = score_control(client, args.offline)
        if control:
            results.append(control)

    if not results:
        raise SystemExit(
            "No transcripts found in outputs/. Run run_session_1.py and run_session_2.py first."
        )

    report = render_report(results, args.offline)
    OUTPUT_DIR.mkdir(exist_ok=True)
    REPORT_PATH.write_text(report + "\n")

    print()
    for r in results:
        pct = "—" if r["pct"] is None else f'{r["pct"]}%'
        print(f'  {r["session"]}: {r["earned"]}/{r["possible"]}  ({pct})')
    print(f"\nReport → {REPORT_PATH}")


if __name__ == "__main__":
    main()
