"""Ground truth and scoring criteria for the New-Hire Onboarding Agent.

Everything here is derived from synthetic-data/. Round 2 deliberately
contradicts round 1, and the whole point of the demo is that the agent notices.
So the rubric is built around that contradiction:

  * Session 1 sees round1 only  -> it should give the OLD process, correctly,
    and it should spot the urgency exception (the asker needs access tomorrow
    but has no tenure).
  * Session 2 sees round2 plus its own Session 1 memory -> it should flag the
    change, give the NEW process, and actively NOT recommend the retired one.

The negative criteria matter more than the positive ones. An agent that recites
the new policy while still telling a new hire to open a #sre-access-requests
ticket has not actually updated its memory — it has appended to it. That is the
exact failure this rubric is designed to catch.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Both sessions ask this, verbatim, so the answers are comparable.
TEST_QUESTION = (
    "I just joined the company and I need read-only prod access to debug an "
    "issue tomorrow. What do I do? Be specific about the steps and the people "
    "I need to talk to."
)


@dataclass
class Criterion:
    """One scored line item.

    `must_match` / `must_not_match` drive the free, offline check.
    `judge_question` is what the LLM judge is asked — it catches paraphrase
    that the regexes miss, and it is the authoritative score when the two
    layers disagree.
    """

    id: str
    session: str
    weight: int
    summary: str
    judge_question: str
    must_match: list[str] = field(default_factory=list)
    must_not_match: list[str] = field(default_factory=list)
    # A criterion the agent gets credit for but is not penalised heavily for
    # missing — nuance, not baseline correctness.
    bonus: bool = False


# --------------------------------------------------------------------------
# Session 1 — baseline. Round 1 documents only, empty memory.
# --------------------------------------------------------------------------

SESSION_1 = [
    Criterion(
        id="s1_channel",
        session="session1",
        weight=2,
        summary="Routes the request through #sre-access-requests",
        judge_question=(
            "Does the answer tell the engineer to open a ticket or request in the "
            "#sre-access-requests Slack channel?"
        ),
        must_match=[r"#?sre-access-requests"],
    ),
    Criterion(
        id="s1_pairing",
        session="session1",
        weight=2,
        summary="Names the SRE pairing session as the gate",
        judge_question=(
            "Does the answer say a pairing session with an SRE is required before "
            "access is filed?"
        ),
        must_match=[r"pair(ing)?\s+session|pair with an SRE|pairing with"],
    ),
    Criterion(
        id="s1_tenure",
        session="session1",
        weight=2,
        summary="States the 2-week tenure requirement",
        judge_question="Does the answer state that read-only access requires 2 weeks of tenure?",
        must_match=[r"2\s*weeks?|two\s*weeks?"],
    ),
    Criterion(
        id="s1_approvers",
        session="session1",
        weight=1,
        summary="Says to tag the manager and the SRE on rota",
        judge_question=(
            "Does the answer say to tag or involve both the engineer's manager and "
            "the SRE on rota for that week?"
        ),
        must_match=[r"manager"],
    ),
    Criterion(
        id="s1_urgent_exception",
        session="session1",
        weight=3,
        summary="Surfaces the urgent 24-hour temporary access exception",
        judge_question=(
            "The engineer just joined (so has no tenure) and needs access TOMORROW. "
            "Does the answer surface the urgent-access exception — that the on-call "
            "SRE can grant temporary 24-hour read-only access without a pairing "
            "session, with the pairing to follow within 5 working days?"
        ),
        must_match=[r"24[- ]hour|urgent|temporary|exception"],
    ),
    Criterion(
        id="s1_rota_lookup",
        session="session1",
        weight=1,
        summary="Points at PagerDuty for the current on-call SRE",
        judge_question=(
            "Does the answer explain how to find who the current on-call/rota SRE is "
            "(the PagerDuty on-call schedule)?"
        ),
        must_match=[r"pagerduty|on-?call schedule|rota"],
        bonus=True,
    ),
    Criterion(
        id="s1_specific",
        session="session1",
        weight=2,
        summary="Concrete rather than generic",
        judge_question=(
            "Is the answer specific — does it name actual channels, tools, roles or "
            "people from the documents, rather than giving generic advice like "
            "'contact your IT department'?"
        ),
    ),
]


# --------------------------------------------------------------------------
# Session 2 — the demo moment. Round 2 documents plus Session 1 memory.
# --------------------------------------------------------------------------

SESSION_2 = [
    Criterion(
        id="s2_change_flag",
        session="session2",
        weight=3,
        summary="Leads by flagging that the policy changed",
        judge_question=(
            "Does the answer OPEN by flagging that the guidance has changed — "
            "contrasting the old policy with the new one — rather than silently "
            "presenting the new process as if it had always been the case?"
        ),
        must_match=[r"⚠|this changed|has changed|changed|supersed|no longer|updated policy"],
    ),
    Criterion(
        id="s2_certification",
        session="session2",
        weight=3,
        summary="Names the Prod Access Foundations certification",
        judge_question=(
            "Does the answer say the engineer must complete the 'Prod Access "
            "Foundations' online course/assessment in the BTS Learning portal?"
        ),
        must_match=[r"prod access foundations|certification|learning portal|course"],
    ),
    Criterion(
        id="s2_iam_platform",
        session="session2",
        weight=3,
        summary="Routes the request through the IAM platform",
        judge_question=(
            "Does the answer say access is requested through the IAM platform, "
            "rather than through Slack?"
        ),
        # Round 1 also says access is filed "in our IAM tool", so a bare /IAM/
        # matches the OLD process too — it scored a false pass in the negative
        # control run. Require the new platform-as-front-door phrasing.
        must_match=[r"IAM platform|IAM portal|through the IAM|via the IAM|request .{0,20}IAM"],
    ),
    Criterion(
        id="s2_just_in_time",
        session="session2",
        weight=2,
        summary="Explains just-in-time, 4-hour scoped access",
        judge_question=(
            "Does the answer explain that access is granted just-in-time and scoped "
            "to a 4-hour window per request, so it must be re-requested?"
        ),
        must_match=[r"just[- ]in[- ]time|\bJIT\b|4[- ]hour"],
    ),
    Criterion(
        id="s2_new_tenure",
        session="session2",
        weight=2,
        summary="States the reduced 3-working-day tenure",
        judge_question=(
            "Does the answer state the tenure requirement is now 3 working days "
            "(reduced from 2 weeks)?"
        ),
        must_match=[r"3\s*working days|three\s*working days|day 4|3 days"],
    ),
    Criterion(
        id="s2_no_stale_process",
        session="session2",
        weight=4,
        summary="Does NOT prescribe the retired Slack/pairing path",
        judge_question=(
            "Does the answer AVOID instructing the engineer to follow the retired "
            "process? Score 0 if it tells them to open a #sre-access-requests ticket "
            "or to book an SRE pairing session as the way to get access NOW. "
            "Referring to the old process only to contrast it with the new one is "
            "correct and should score full marks."
        ),
    ),
    Criterion(
        id="s2_no_stale_org",
        session="session2",
        weight=2,
        summary="Does NOT use pre-re-org job titles",
        judge_question=(
            "Does the answer AVOID stale titles from the May 2026 re-org? Score 0 if "
            "it calls Anika Reddy 'Head of Engineering' (she is Chief AI Officer) or "
            "Tom Bryce 'Engineering Ops Lead' (he is Head of Platform; Priya Shah "
            "holds Eng Ops Lead)."
        ),
        must_not_match=[
            r"anika[^.\n]{0,40}head of engineering",
            r"tom bryce[^.\n]{0,40}(engineering ops|eng ops)",
        ],
    ),
    Criterion(
        id="s2_tenure_gate",
        session="session2",
        weight=2,
        summary="Notices 'tomorrow' may not clear the 3-day gate",
        judge_question=(
            "The engineer JUST joined and needs access TOMORROW, but the new policy "
            "requires 3 working days of tenure. Does the answer notice this gap and "
            "address it, rather than implying access is available immediately?"
        ),
        bonus=True,
    ),
    Criterion(
        id="s2_specific",
        session="session2",
        weight=2,
        summary="Concrete rather than generic",
        judge_question=(
            "Is the answer specific — naming the actual course, platform, and people "
            "from the documents rather than giving generic advice?"
        ),
    ),
]


ALL_CRITERIA = SESSION_1 + SESSION_2


def for_session(session: str) -> list[Criterion]:
    return [c for c in ALL_CRITERIA if c.session == session]


def max_score(criteria: list[Criterion]) -> int:
    """Criteria are scored 0-2, so the ceiling is twice the summed weight."""
    return sum(c.weight for c in criteria) * 2
