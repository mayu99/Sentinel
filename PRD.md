# Sentinel — PRD

Status: draft, hackathon scope. Built on top of the existing `README.md` thesis/architecture — this document does not re-decide the architecture, it specs what's underspecified and cuts what doesn't need to exist.

**Judging thesis, as given:** "build a cool, real-world problem-solving solution with RocketRide." No rubric or weighting was provided beyond that. This PRD optimizes for: (1) a real, specific problem, (2) an architecture that's legibly RocketRide-native, (3) a demo that survives being poked live. It does not optimize for feature count.

**Demo format, as given:** recorded video as the primary artifact, plus live Q&A where judges may ask to see something again or ask follow-up questions. This means: script the recording tightly, but the underlying pipelines still have to survive being re-run or prodded live — "it worked once when we recorded it" is not sufficient.

**Console, as given:** aspirational only — CUT/NICE, not MUST-SHIP. No custom UI ships. The demo surface is RocketRide's own dashboard/trace view plus the raw `incidents/*.md` files.

**Incident file store location, as given:** unconfirmed. `tool_filesystem`'s write path has no `path` field in the current config and no schema file exists in this repo to confirm a default (see audit finding, carried into Open Questions §10). Nothing below assumes a specific path exists on the host filesystem until this is confirmed.

---

## 1. Problem statement

A dbt or Airflow job fails overnight. The on-call data engineer is paged, opens the failure, and spends **30–60 minutes** (README's own figure — not re-derived here, no additional frequency/cost data exists in this repo, so no further quantification is claimed) doing three manual things every time:

1. Reading the error and log excerpt to find which model and object failed.
2. Manually querying the warehouse to check whether an upstream table's schema changed underneath the model — the actual root cause is almost never in the error message itself, it's in the live schema.
3. Writing up what happened, so the next person (or the same person, three incidents later) isn't re-diagnosing the same class of failure.

That 30–60 minutes happens at 3am, is undocumented unless the engineer chooses to write it up, and the write-up — when it happens — usually isn't structured enough to answer "have we seen this pattern before?" without someone re-reading a pile of Slack threads.

Sentinel's bet: steps 2 and 3 are almost entirely mechanical — fetch live schema, diff against what the model expects, write it down — and don't need a human in the loop for the *first draft*. The human still reviews and ships the fix.

## 2. Users

**Primary: on-call data engineer.** Gets paged, wants to know root cause and the fix, fast, without opening a SQL client at 3am. Consumes the triage agent's output directly (Slack summary + incident report).

**Secondary: data platform lead.** Doesn't get paged. Cares about patterns across incidents — "is this the third column-rename incident this month, and should we add a schema contract instead of fixing these one at a time." Consumes the postmortem agent's digest, not individual incident reports.

## 3. Goals and non-goals

### Goals

- G1: A failure event → live-warehouse-grounded root cause → written incident report → optional Slack notification, fully automated, on RocketRide, with zero bytes leaving the network (local Ollama).
- G2: A second, independently-invocable RocketRide pipeline that reads back incident reports and synthesizes a cross-incident digest — proving the two-pipeline, shared-file-state architecture actually composes, not just that one pipeline works.
- G3: The RocketRide node graph itself is the legible artifact — a judge can open the `.pipe` file in the canvas and understand the system without reading code.
- G4: The demo survives being re-run or interrupted live, because live Q&A is part of the judging format.

### Non-goals (explicit cuts, hackathon scope)

- NG1: **No custom Console/UI.** Confirmed CUT/NICE per product decision above. RocketRide's dashboard and raw markdown files are the entire viewing surface for MUST-SHIP.
- NG2: **No multi-warehouse support.** Postgres only. `db_clickhouse`/`db_mysql` stay README's "extension points" prose, not code.
- NG3: **No Airflow-native ingestion.** The webhook accepts dbt-shaped JSON via the replay script. A real Airflow `on_failure_callback` integration is not built.
- NG4: **No auth, no multi-tenant, no multi-team routing.** One warehouse, one Slack channel, one API key.
- NG5: **No incident database/index.** Flat markdown files in a directory, full stop. No SQLite, no Postgres table of incidents.
- NG6: **No specialized diagnosis per error class.** The agent reasons zero-shot over whatever error text and schema it's given. No hardcoded "if error contains X, check Y" branches beyond what's already in the agent's prose instructions.
- NG7: **No automated fix application.** The agent proposes a SQL/config fix as text. It never opens a PR, never runs a migration, never touches the dbt project.
- NG8: **No test suite for the pipelines.** They're `.pipe` JSON files; the closest thing to a test is the demo replay script and manual observation of the trace.
- NG9: **No production secrets management.** `.env` / RocketRide env config only.
- NG10: **No handling of concurrent incidents.** The triage pipeline assumes one failure at a time; no queueing or dedup logic if the webhook is hit twice in quick succession.

## 4. User stories

**Triage (primary user, on-call engineer):**
- As an on-call engineer, when a dbt/Airflow job fails, I want the failure automatically triaged against the live warehouse schema — not just the error text — so the root cause I'm handed is actually verified, not a guess.
- As an on-call engineer, I want a Slack summary under 120 words with root cause + fix so I can decide "ship the one-liner now" vs "this needs a human" without opening a file.
- As an on-call engineer, if the agent can't determine a root cause, I want it to say so explicitly and list what it ruled out, so I don't mistake silence or a vague answer for "nothing's wrong."

**Postmortem digest (secondary user, data platform lead):**
- As a platform lead, I want to ask "digest of this week's incidents" and get incident count, affected models, and recurring root-cause patterns, so I can decide where to invest in prevention (e.g. schema contracts) instead of reacting incident-by-incident.
- As a platform lead, I want the single highest-leverage preventive action stated concretely, not a list of generic suggestions.
- As a platform lead, if there are no incidents in the window I asked about, I want to be told that plainly, not given a fabricated summary.

**Console viewing — NICE/CUT, speculative, not committed:**
- *(If built post-hackathon)* As a judge or engineer, I want to see a timeline of what the triage agent did — parse, schema lookup, diagnosis, fix — without reading raw trace JSON. This is explicitly not in MUST-SHIP; written here only so the schema in §7 is designed to make it possible later.

## 5. Feature list

Time estimates are rough sizes (S ≈ under 1 hr, M ≈ 1–3 hrs, L ≈ half a day+), not hours-remaining-aware — the actual runway wasn't specified, so treat these as relative sizing to sequence work, not a committed schedule.

| Feature | Tier | Est. | Note |
|---|---|---|---|
| Triage pipeline runs end-to-end against seeded drift (webhook → agent → schema lookup → report → optional Slack) | MUST | L | This is the whole thesis. Everything else is secondary. |
| Incident report written to disk in the schema defined in §7 | MUST | S | Currently the agent instructions describe content in prose, not a literal template — needs the template folded into the instructions. |
| Postmortem pipeline reads reports and produces a digest | MUST | M | Already wired; needs the schema from §7 to synthesize reliably. |
| Confirm `tool_filesystem` write path (host-visible? which directory?) | MUST | S | Blocks trusting the recorded demo shows a real, inspectable file — see §10. |
| Recorded demo video following the §9 script | MUST | M | The primary submission artifact per the demo-format answer. |
| Fix `${ROCKETRIDE_PG_*}` env prefix + required top-level `.pipe` fields | MUST | S | Already done in this repo (prior session) — listed for completeness. |
| Graceful behavior for the 5 failure states in §8 | MUST | M | Live Q&A means judges may trigger one of these by accident (e.g. asking to re-run without Ollama warm). |
| Verify webhook payload shape (`fire_failure.py` posts `{"question": ...}` to a `webhook` source) actually reaches the agent as `questions` lane | MUST | S | Flagged as unverified in the prior audit — this is load-bearing for the entire demo and must be confirmed by an actual run, not assumed. |
| Slack notification on success | NICE | S | Already wired, degrades gracefully per instructions text — but "degrades gracefully" itself is unverified (see §8). Nice because the demo works without it. |
| Second seeded failure scenario (different error class, e.g. permission error) | NICE | M | Would make the postmortem digest's "recurring pattern" claim more convincing with >1 pattern, but one scenario is enough to prove the mechanism. |
| Custom Sentinel Console (incident list + timeline UI) | CUT | L+ | Explicitly out of scope per product decision. Don't start this. |
| Airflow `on_failure_callback` adapter | CUT | M | README extension point only. |
| Multi-warehouse (`db_clickhouse`/`db_mysql`) | CUT | M | README extension point only. |
| Automated fix PR creation | CUT | L | Out of scope (NG7), and a bigger trust problem than this hackathon should take on. |

## 6. Functional requirements — per MUST-SHIP feature

**Triage pipeline end-to-end**
- FR1.1: Given the seeded drift (`raw.customers.customer_email` renamed to `email`, `stg_customers.sql` unchanged), a POST of `demo/failure_payload.json` to the triage webhook results in a completed agent run without manual intervention.
- FR1.2: Every column-existence claim in the output must be traceable to a `warehouse.get_schema` call in that run's trace — this is already stated as a hard rule in the agent's instructions ("Never invent schema details"); it must hold up when someone actually reads the trace, not just when the instructions say so.
- FR1.3: The proposed fix is a concrete SQL diff (the exact line to change), not a general recommendation.
- FR1.4: The proposed guardrail is a specific, nameable mechanism (e.g. "add a dbt source freshness/contract test on `raw.customers.email`"), not "be more careful."

**Incident report written to disk**
- FR2.1: File is written to `incidents/<UTC-ISO-timestamp>-<model>.md` (matches both agents' instructions verbatim — do not diverge from this naming, the postmortem agent's filter-by-timestamp-in-filename logic depends on it).
- FR2.2: Content conforms to the schema in §7, well enough that the postmortem agent's `fs.read`-and-quote-verbatim behavior produces a coherent quote every time, not just when the model happens to format well.

**Postmortem digest**
- FR3.1: `fs.list` against the incident directory before reading — the agent must not assume files exist.
- FR3.2: Digest cites specific report contents (root cause sentences, affected models) rather than paraphrasing from memory of the conversation.
- FR3.3: Empty/missing directory produces an explicit "no incidents found" answer (already in the agent's instructions — verify it holds against an actually-empty directory, not just against the seeded demo state).

**Confirm `tool_filesystem` write path**
- FR4.1: Before the recording, run the triage pipeline once and locate the written file on the host filesystem by hand (not by trusting the agent's own claim that it wrote something). Record the actual path.
- FR4.2: If the path is not host-visible (e.g. sandboxed inside the RocketRide server process), the demo script in §9 must show the file via whatever channel *is* available (agent's own `fs.read` echoed back, or the postmortem agent quoting it) instead of `cat`-ing a file that doesn't actually exist where a viewer would expect.

**Failure-state handling** — see §8, each state gets its own requirement there.

**Webhook payload shape verification**
- FR6.1: Run `scripts/fire_failure.py` against a started `sentinel-triage.pipe` and confirm in the trace that the agent actually received the full JSON payload as its question text (per the script's docstring claim) — not a truncated or mis-parsed version. This is a run-and-observe requirement, not a docs-verification one; the RocketRide docs don't specify the webhook HTTP body contract precisely enough to confirm from reading alone (see §10).

## 7. Incident report schema

No literal template exists today — the agent's instructions describe *content* requirements in prose (falsifiable root-cause sentence, minimal fix, one guardrail) but never hand the model a markdown skeleton to fill in. Since the postmortem agent has to reliably `fs.read` and quote from these files, and any future Console has to parse them, that's a gap worth closing here rather than leaving to whatever an 8B local model free-forms.

Design constraint: an 8B local model will drift from a rigid template under prose instructions alone. Keep the schema to a small number of fixed `##` headers (models follow heading discipline better than they follow nested YAML), skip strict frontmatter, and treat downstream parsing as line/section-based, not strict-schema.

```markdown
# Incident: <failed_model> — <UTC timestamp>

**Job:** <orchestrator> / <job name>
**Failed model:** <failed_model>
**Downstream skipped:** <comma-separated list, or "none">
**Detected:** <UTC timestamp, ISO 8601>

## Root Cause

<Single falsifiable sentence. Must name the specific object(s) and the specific
change, e.g. "Upstream table raw.customers renamed customer_email to email;
stg_customers.sql still selects customer_email.">

## Evidence

<What warehouse.get_schema / warehouse.get_data actually returned that supports
the root cause above. This section exists so a human — or the postmortem
agent — can verify the claim instead of trusting it blindly.>

## Fix

<The exact SQL or config change. Code block, not prose description.>

## Guardrail

<One specific, nameable preventive mechanism — a named test, a contract, a
monitor. Not "add more testing.">

## Status

**Root cause determined:** yes | no
**Notified:** slack | none
```

Notes on this schema:
- The filename (`incidents/<UTC timestamp>-<model>.md`) already carries the timestamp and model — repeating them in the H1 and metadata block is deliberate redundancy so the file is self-describing even if moved or renamed, and so any future parser can extract fields two ways.
- `Root cause determined: no` is a first-class, expected value — this is where the "if you cannot determine the root cause, say so" instruction lands structurally, instead of producing a report that looks successful when it isn't.
- This template needs to be pasted into `sentinel-triage.pipe`'s agent `instructions` array (step 5, "RECORD") to actually take effect — writing it in this PRD doesn't change agent behavior by itself. That's a follow-up edit, not done as part of this PRD.

## 8. Failure states

| State | Current spec'd behavior | Gap |
|---|---|---|
| **Ollama down** | None documented. RocketRide has no documented LLM fallback/retry chain. | Not spec'd anywhere. Required: the pipeline run should fail visibly (task ends in error, non-empty `exitMessage` per the Observability doc's `TASK_STATUS.exitCode`/`exitMessage`), not hang silently. Recommend a pre-flight check in the demo script (confirm `localhost:11434` responds) before recording — this is a setup-time mitigation, not a runtime one, since no documented runtime fallback exists. |
| **Postgres unreachable** | Agent instructions never mention what to do if `warehouse.get_schema`/`warehouse.get_data` itself errors — only "never invent schema details" and "if you cannot determine root cause, say so." | Gap: those two instructions together *imply* the right behavior (tool error → can't verify schema → say so) but it's not stated explicitly. Add an explicit line: "If warehouse.get_schema or warehouse.get_data fails or times out, state that the warehouse was unreachable as the blocking issue — do not proceed to a root-cause guess without it." |
| **Agent can't determine root cause** | Already spec'd: "If you cannot determine the root cause, say so and list what you ruled out." Report is still written (RECORD is step 5, unconditional in the instruction ordering). | No gap in instructions. Verify in practice: confirm a deliberately-unsolvable payload still produces a written report with `Root cause determined: no`, not a silent failure. |
| **`incidents/` empty or missing** | Already spec'd on the postmortem side: "If incidents/ is empty or missing, say so plainly. Never invent incidents." | No instruction gap. Depends on FR4.1 (confirmed file path) to even test this meaningfully. |
| **Slack token missing** | README: "without it the agent skips the notify step." Agent instructions: "If Slack tools are available, post... If Slack is not available, skip without failing." `.env.example` ships `ROCKETRIDE_SLACK_TOKEN=` empty. | Real gap: `tool_slack_1` is unconditionally wired into the pipeline regardless of whether the token is set — the instructions rely on the agent inferring "Slack is not available" from something, but what that something is (a tool-call error it catches, vs. a structural signal it can see before calling) is undocumented, because `tool_slack` isn't documented at all (per prior audit). Must verify by running with an empty token: does the agent skip cleanly, or does it attempt the call and get a raw tool error that it then has to reason around? If the latter, the instructions need an explicit "if the Slack tool call errors, treat that as unavailable and continue" line. |

## 9. What a judge should see in 3 minutes

Recorded video, ~3 minutes, matching the demo-format answer (recorded primary + live Q&A tolerance):

1. **0:00–0:20 — Hook.** One sentence on the 3am problem (30–60 minutes of manual grep-and-guess), stated plainly, no slide deck.
2. **0:20–0:45 — Architecture in one screen.** Open `sentinel-triage.pipe` in the RocketRide canvas. Point at: local Ollama (no data leaves the network), the tool fan-out (warehouse, python sandbox, filesystem, Slack), memory. One sentence: "this whole system is this file."
3. **0:45–1:45 — Fire the failure, live.** Run `fire_failure.py` against the started pipeline. Show the RocketRide dashboard/trace live (contingent on §10's open question about whether the extension's default run sets a trace level that surfaces `FLOW` events — confirm this *before* recording, don't discover it live). Narrate what's on screen: agent reads the payload, calls `warehouse.get_schema('raw.customers')`, the schema shows `email` not `customer_email`, agent states the root cause.
4. **1:45–2:15 — Proof of output.** Show the actual written incident report (via whatever channel FR4.2 establishes is real) and, if the Slack token is configured for the recording, the `#data-incidents` message landing.
5. **2:15–2:50 — Postmortem, independently.** Start `sentinel-postmortem.pipe`, open its chat, ask "digest of this week's incidents," show it citing the specific report back.
6. **2:50–3:00 — Close.** One sentence: two composable RocketRide pipelines, zero hosted-LLM calls, the investigation itself is auditable.

Cut anything that requires narrating RocketRide concepts the judge hasn't seen yet (lanes, control-plane wiring) — show, don't explain, unless a judge asks in live Q&A.

## 10. Open questions

These are blocking or near-blocking, not cosmetic. Ranked by how much they threaten the recorded demo:

1. **Does the RocketRide VS Code extension's default "run" set a `pipelineTraceLevel` that produces `apaevt_flow` events?** Per `ROCKETRIDE_OBSERVABILITY.md`, `FLOW` events require the *executor* to pass `pipelineTraceLevel` at `execute` time, and the default is `none`. Nothing in the docs read for this project confirms what the VS Code extension passes when you click "start." If it's `none`, README's "watch the dashboard, see the trace" demo beat (and §9 step 3 above) shows nothing. **Must confirm by actually running it before recording.**
2. **Where does `tool_filesystem` actually write, and is it host-visible?** No `path` field in the current config, no schema file in this repo to check a default. Confirmed unverifiable from docs alone in the prior audit. Blocks FR4.1/FR4.2 and any future Console.
3. **Does `fire_failure.py`'s raw HTTP POST (`{"question": <payload>}` to the webhook URL) actually deliver the payload as the `questions` lane the agent expects, or does it hit a lane/parsing mismatch?** The RocketRide docs model `webhook` sources as producing a `tags` lane by default (raw file/payload metadata), routed through `parse` before becoming text/questions — yet `sentinel-triage.pipe` wires `agent_rocketride_1`'s input directly as `{"lane": "questions", "from": "webhook_1"}`, and the replay script bypasses the SDK's `send()`/`sendFiles()` methods entirely in favor of a raw POST with a `question` key (a body shape not documented anywhere in the Python/TypeScript API docs). Both of these were flagged as unverified in the prior pipeline audit. This is the single highest-risk unknown in the whole demo — if it's wrong, step 3 of §9 doesn't work at all, live or recorded.
4. **Does `tool_slack` fail cleanly (agent catches and skips) or noisily (raw tool error surfaces in the agent's reasoning) when the token is empty?** Determines whether the "Slack notify" happy path in §9 step 4 needs the token configured for recording, or whether an unconfigured token would visibly break the run.
5. **What is the actual time budget?** Not established — the feature-list estimates in §5 are relative sizes, not a schedule, because runway wasn't specified. Whoever picks this up next should fix a deadline before treating the MUST list as a literal to-do queue.

None of the above were guessed at or silently resolved in this document — each is called out here specifically so they get answered before being treated as settled.
