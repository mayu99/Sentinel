# Sentinel — Session Handoff

Status as of git HEAD `6609c40` ("docs: rewrite README with architecture, falsification test, and honest scope"). Pipeline is working end to end. This document replaces all prior handoff notes; nothing outside this file should be treated as current.

---

## Corrections to the Previous Handoff

Read this section first. Each item below was recorded incorrectly in an earlier version of this document, written mid-debugging before the relevant thing was actually run. A later session lost a day relitigating these because the earlier doc stated them as settled. They are now settled — the other way.

1. **Webhook → agent wiring (old §4): HALF WRONG.** The old doc said "`webhook → questions → agent` wiring is valid, do NOT add `parse` or `question` nodes." The `questions` lane does exist on `webhook` in the services catalog, but nothing a plain HTTP client can actually send ever populates it — the webhook routes an incoming request body to an output lane **by MIME type**, and `text/*` lands on the `text` lane, not `questions`. A `question` node (classType `text`, palette category TEXT) **is** required, wired `webhook.text → question → agent.questions`. The `parse` node is, and always was, **not** required — its output lanes (`text`, `table`, `image`, `video`, `audio`) do not include `questions`. See §4 below and `TROUBLESHOOTING.md` item 1.

2. **`?auth=<key>` query param (old §3.11): WRONG.** The old doc said this is rejected. It is not — the RocketRide Endpoint Configuration dialog offers it directly as a supported auth mode. Both `?auth=<key>` and `Authorization: Bearer <key>` work. See §3.11.

3. **File store access (old §7): WRONG.** The old doc said the incident file store is reachable only through the client SDK's `fs_*` methods. It is a plain directory on disk — `~/.rocketlib/store/users/local/files/` — readable with any file tool, no SDK required. This unblocks the Console idea that was deferred in old §9 for exactly this reason. See §7 and §9.

4. **Persistent `raw.customers does not exist` warning (old §3.8): RESOLVED.** RocketRide's `db_postgres` node resolves unqualified table names against the `public` schema, not `raw`. The demo table has been moved to `public`, and `demo/seed.sql` now creates it there. Querying `customers` unqualified (or `public.customers` explicitly) works; querying `raw.customers` does not, by design. See §3.8.

5. **Tool names (old §3.6): VERIFIED, previously UNVERIFIED.** `postgres.get_schema`, `postgres.get_data`, `python.execute`, `fs.write`, and `slack.http_request` all resolve and execute correctly — confirmed by successful runs, not by reading the schema. See §3.6.

6. **Open webhook bug (old §5): CLOSED.** Was the same issue as correction 1. Fixed by the `question` node; see §4.

---

## 1. The Hard Rule

The agent must never be told the answer. The failure payload may contain the failing column name and the error text, but nothing about what replaced it. The agent is required to query the live warehouse to find out — every column-existence claim in its output must trace to a `postgres.get_schema` call in that run's trace.

**This rule was silently violated for days.** `demo/failure_payload.json` originally carried a real Postgres `HINT: Perhaps you meant to reference the column "customers.email"` line inside the `error` field. It looked like realistic error output — which it was — but it also handed the agent the answer directly, so a run that never queried the schema could still produce a correct-looking diagnosis. The HINT line has been removed. **Do not reintroduce it.** If the payload is ever regenerated from a real Postgres error, strip the `HINT:` clause before saving.

The only reliable way to verify this rule actually holds, as opposed to holding by coincidence, is the falsification test in §6. Run it after any change to the agent's instructions, the payload, or the schema tools.

## 2. Architecture

Two RocketRide pipelines:

- **`pipelines/sentinel-triage.pipe`** — event-driven. `webhook → question → Sentinel Triage Agent → response`. Tools: Warehouse (Postgres), Python Sandbox, Incident Store (filesystem), Slack Webhook (HTTP). LLM: Gemini (`custom` profile). Six-step protocol, see §2.1.
- **`pipelines/sentinel-postmortem.pipe`** — on-demand. `chat → Sentinel Postmortem Agent → response`. Tool: Incident Store (read-only usage). LLM: Ollama (local, still wired — see §5.3).

### 2.1 The six-step triage protocol

1. **PARSE** — read the failure payload, identify the failed model and error class.
2. **INSPECT SOURCE** — query live schema via `postgres`, using `string_agg(column_name, ', ')` (see §3.7 — do not request raw multi-row output).
3. **DIAGNOSE DRIFT** — diff what the model's SQL expects against the live schema, via `python.execute`. State root cause as one falsifiable sentence.
4. **PROPOSE FIX** — minimal concrete SQL/config change, plus one specific, nameable guardrail.
5. **RECORD** — write the incident report to `incidents/<UTC timestamp>-<model>.md` via `fs.write`. Filename must contain only letters, digits, hyphens, underscores — colons in the timestamp must be stripped (`2026-08-09T031241Z`, not `2026-08-09T03:12:41Z`).
6. **NOTIFY** — POST `{"text": "<summary>"}` via `slack.http_request`. See §5.2 for the current target URL.

## 3. RocketRide Runtime Notes

### 3.3 `${VAR}` interpolation

Works in node **CONFIG** fields (e.g. `db_postgres`'s `host`/`database`/`user`/`password`, `llm_gemini`'s `apikey`). Does **not** work in agent **instruction text** — a `${VAR}` placed inside an instruction string is passed through to the LLM as the literal, unexpanded characters `${VAR}`, not the variable's value. This is why the Slack notify URL is hardcoded rather than templated — see §5.2.

### 3.4 Gemini model dropdown

The dropdown lists only retired or grandfathered models (`gemini-2.0-flash` 404s as retired; `gemini-2.5-flash` is unavailable to new accounts). Use the `custom` profile and set the model name directly. Free tier caps at **20 requests/day, per project, per model** — burning requests across multiple model names while testing exhausts the quota fast, and looks like a different bug (rate limiting) if you don't know this going in.

### 3.5 Ollama node

Present on both pipeline canvases, deliberately left unwired to the triage agent's `llm` control (proof the LLM is a single swappable node, not load-bearing). Still wired on the postmortem pipeline — see §5.3.

### 3.6 Verified tool names

`postgres.get_schema`, `postgres.get_data`, `python.execute`, `fs.write`, `slack.http_request` — all confirmed resolving and executing correctly by successful runs. (Corrected from "unverified" — see Corrections §5 above.)

### 3.7 Postgres result truncation

Multi-row results from `postgres.get_schema` are truncated to a **two-row preview** before reaching the LLM. This is a tool-output limit, not a query problem, and it is easy to mistake for a schema-reading bug. Workaround: aggregate server-side to a single value —
```sql
SELECT string_agg(column_name, ', ' ORDER BY ordinal_position)
FROM information_schema.columns WHERE table_name = '<t>';
```
One row back, no truncation. This is now baked into the agent's step-2 instructions, not left to be rediscovered per run.

### 3.8 Schema resolution — `public` vs `raw`

`db_postgres` resolves unqualified table names against `public`. The demo table lives in `public.customers`; a `raw.`-qualified reference does not resolve and produces a persistent "table does not exist" warning. (Corrected from "open issue" — see Corrections §4 above.)

### 3.9 Tool-call required arguments

`python.execute` requires a non-empty `code` argument; `fs.write` requires a non-empty `path`; `slack.http_request`/`tool_http_request` requires an explicit `method`. The agent's instructions now say so explicitly per-tool, because early runs occasionally called these with the argument missing or empty and produced a hard tool error mid-wave rather than a graceful skip.

### 3.10 File store location

Real directory: `~/.rocketlib/store/users/local/files/` (equivalently `%LOCALAPPDATA%\..\.rocketlib\store\users\local\files\` on Windows). Readable with any file tool — `ls`, a text editor, whatever. (Corrected — see Corrections §3 above.)

### 3.11 Auth

`Authorization: Bearer <key>` and the `?auth=<key>` query param both work; the latter is directly offered by the Endpoint Configuration dialog in the canvas, not a workaround. (Corrected — see Corrections §2 above.)

## 4. Webhook Wiring — CLOSED

The webhook source routes an incoming HTTP request body to an output lane by MIME type: `text/*` → `text` lane; other types → other lanes; nothing routes a plain request to `questions` directly for a normal client. `sentinel-triage.pipe` now wires:

```
webhook (text lane) → question (text → questions) → Sentinel Triage Agent (questions)
```

Callers must POST with `Content-Type: text/plain`. `scripts/fire_failure.py` does this. The `parse` node is not part of this chain and never needs to be — it exists for document/file-upload ingestion (PDFs, images), not for routing plain text/JSON payloads to an agent. Full detail in `TROUBLESHOOTING.md` item 1.

## 5. Known Issues

### 5.1 Webhook lane bug

CLOSED. Was correction 1 / §4 above.

### 5.2 Slack notify target is hardcoded — OPEN, must fix before repo goes public

Because `${VAR}` doesn't interpolate in instruction text (§3.3), the NOTIFY step's target URL is a literal string hardcoded directly into the agent's step-6 instruction in `pipelines/sentinel-triage.pipe`, currently pointed at a `webhook.site` test endpoint rather than `${ROCKETRIDE_SLACK_WEBHOOK}` or a real Slack incoming webhook. The `tool_http_request` node's `urlWhitelist` allows both `hooks.slack.com` and `webhook.site`. The request shape (`{"text": "<summary>"}`, POST) is identical either way — swapping targets is a one-line edit to the instruction text, not a rewiring. **Must be replaced with a placeholder or removed before the repo goes public**, since a live webhook.site URL in a public repo is an open drop-box for anyone who finds it.

### 5.3 Postmortem pipeline drift

`sentinel-postmortem.pipe` is still wired to `llm_ollama_1` (never swapped to Gemini like the triage pipeline was), and still carries stale `formDataValid` canvas flags from before the last round of edits. Neither blocks the postmortem pipeline from running; both are cleanup, not bugs.

## 6. The Falsification Test — standard check

This is the only verification that the hard rule (§1) actually holds, rather than holding by coincidence. Run it after any change to the agent's instructions, the payload, or the schema tools:

```bash
docker exec sentinel-warehouse psql -U sentinel -d warehouse -c \
  "ALTER TABLE customers RENAME COLUMN email TO contact_email"
python scripts/fire_failure.py
docker exec sentinel-warehouse psql -U sentinel -d warehouse -c \
  "ALTER TABLE customers RENAME COLUMN contact_email TO email"
```

If the agent's diagnosis still says `email` (or anything not `contact_email`), it is reading the payload, not the schema — that is a hard failure of §1, not a cosmetic issue. Passing result is committed at `demo/sample_output/falsification-test-contact_email.md`.

## 7. File Store — RESOLVED

See §3.10. This was previously believed to require SDK access; it does not. This resolves the blocker that had deferred the Console idea in §9.

## 8. PowerShell Gotchas

- No `<` input redirection. `docker exec -i ... < file.sql` fails with `The '<' operator is reserved for future use.` Use `Get-Content file.sql | docker exec -i ...` instead. (This is how `demo/seed.sql` must be loaded.)
- No `&&`. Chain with `;` or `A; if ($?) { B }`.
- `Set-Content -Encoding utf8` writes a BOM. Use `[System.IO.File]::WriteAllText(...)` or `-Encoding utf8NoBOM` (PowerShell 6+) when the consumer doesn't expect one.

## 9. Console / Future UI — deferred, no longer blocked

Out of scope per the PRD (NG1, explicit CUT/NICE, not MUST-SHIP for the hackathon). Previously also blocked on an incorrect belief that the incident store needed SDK access to read (see Corrections §3). That blocker is gone — §3.10/§7 confirm it's a plain directory. Still not started; still not required for the current deliverable.

## 10. Current State

Working end to end. 7/7 consecutive runs, 7/7 correct diagnoses, 7/7 notifications delivered (to the §5.2 target). Zero errors in the trace in the final configuration. All six protocol steps (§2.1) complete on every run: parse, inspect live schema, diagnose drift, propose fix, write incident report, notify via HTTP POST. Typical run: 22–35 seconds, 25–65 tool calls, one wave loop. Fastest clean run: 6.7 seconds, 29 calls. The agent self-corrects malformed tool calls within the wave loop without failing the run.

Committed through git HEAD `6609c40`. Key commits, oldest to newest: `41e72c0` initial skeleton → `fac22c4`/`bac2708` pipeline schema fixes → `4eb23ff` Gemini swap, Ollama left unwired → `8e1093d` webhook fixed via question node (§4) → `20403f0`/`da1c81c` first working end-to-end run + falsification test passing → `c54129a` tool-argument fixes, zero-error run → `6f9cff5` TROUBLESHOOTING.md written → `6609c40` README rewritten.

## 11. Remaining Work, in Order

1. **Replace the hardcoded `webhook.site` URL** in the triage agent's step-6 instruction with a placeholder (or remove the NOTIFY step's live target) before the repo goes public. See §5.2. **Not done.**
2. **Demo video.** Not recorded. README's Demo Video section is a placeholder pending this.
3. **File a bug report with RocketRide** (Discord) for the `${VAR}`-does-not-interpolate-in-instruction-text behavior (§3.3) — it is undocumented and cost real debugging time.
4. **Postmortem pipeline cleanup** (§5.3): swap `llm_ollama_1` for Gemini to match the triage pipeline, and clear the stale `formDataValid` flags.

**Already done, do not re-do:** README rewrite (git `6609c40` — was previously listed as remaining work; it is finished) and `TROUBLESHOOTING.md` (git `6f9cff5`, covers all ten items enumerated across §§3–8 above in more detail with exact commands).
