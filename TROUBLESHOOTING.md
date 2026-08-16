# Troubleshooting

Known walls hit while building this demo, and how to get past them on a fresh clone.

## 1. Webhook POST returns `objectsCompleted:1` but the agent produces 0 tokens

**Symptom:** POST to the triage webhook returns HTTP 200, `{"objectsRequested":1,"objectsCompleted":1}`, but the response has no `answers` and the trace shows the agent never ran.

**Root cause:** The webhook source routes request bodies to output lanes by MIME type — `text/*` lands on the `text` lane, and there is no config field that routes a JSON body straight to `questions`. Posting `Content-Type: application/json` (or anything other than `text/*`) sends the body to a lane nothing downstream is wired to, so the object completes ingestion but never reaches the agent.

**Fix:** `sentinel-triage.pipe` wires `webhook.text -> question -> agent.questions` (a `question` node, classType `text`, palette category TEXT, sits between the webhook and the agent). Callers must POST with `Content-Type: text/plain`. `scripts/fire_failure.py` does this — see below.

## 2. Auth: Bearer header vs `?auth=` query param

**Symptom:** Requests with `?auth=<key>` look like they should be rejected based on earlier notes in this repo.

**Root cause:** Those earlier notes were wrong. Both work.

**Fix:** Use `Authorization: Bearer <key>` (what `fire_failure.py` uses) or the `?auth=<key>` query param — the Endpoint Configuration dialog in the RocketRide canvas offers the query-param form directly, so it's supported, not a workaround.

## 3. "Can't read the file store without the SDK"

**Symptom:** Assuming incident reports under `incidents/` are only reachable through the RocketRide SDK/API.

**Root cause:** Earlier notes claiming SDK-only access were wrong.

**Fix:** The file store is a real directory on disk:
```
C:\Users\HP\.rocketlib\store\users\local\files\
```
Read it directly — `ls`, a text editor, whatever.

## 4. `postgres.get_schema` only shows 2 rows for a table with more columns

**Symptom:** The agent's schema inspection of a table with more than 2 columns comes back truncated, and root-cause reasoning based on "columns I can see" is wrong or incomplete.

**Root cause:** Multi-row results from `postgres.get_schema` are truncated to a two-row preview before reaching the LLM. This is a tool-output limit, not a query problem.

**Fix:** Aggregate server-side to a single value instead of relying on the raw multi-row result:
```sql
SELECT string_agg(column_name, ', ' ORDER BY ordinal_position)
FROM information_schema.columns WHERE table_name = '<t>';
```
One row back, no truncation.

## 5. `raw.customers` — "relation does not exist" / empty reads

**Symptom:** Agent's `postgres.*` calls against `raw.customers` return a persistent "table does not exist" warning, or reads come back empty even though the table was seeded.

**Root cause:** The demo table lives in schema `public`, not `raw`. RocketRide's `db_postgres` node resolves unqualified table names against `public`; a `raw.`-qualified name doesn't resolve there.

**Fix:** Query `customers` unqualified (or `public.customers` explicitly), not `raw.customers`. `demo/seed.sql` creates the table under `public`.

## 6. Agent's root cause looks suspiciously like it just read the error message

**Symptom:** The agent states the exact replacement column name without any `postgres.get_schema` call showing up in the trace for it — FR1.2 ("every column-existence claim must trace to a `get_schema` call") silently fails.

**Root cause:** `demo/failure_payload.json` used to carry a Postgres `HINT` line naming the replacement column directly in the `error` field (`HINT: Perhaps you meant to reference the column "customers.email".`). The agent could answer from the payload alone, without inspecting live schema.

**Fix:** The HINT line has been removed from `demo/failure_payload.json`. **Do not reintroduce it** — if you regenerate this payload from a real Postgres error, strip the `HINT:` clause before saving.

## 7. Gemini: every model in the dropdown 404s or won't activate

**Symptom:** Selecting `gemini-2.0-flash` fails with a 404-style "model retired" error. `gemini-2.5-flash` shows as unavailable for the account.

**Root cause:** The RocketRide model dropdown lists only retired or grandfathered Gemini models.

**Fix:** Use the `custom` profile and set the model name yourself. Also note: the free tier caps at 20 requests/day, **per project, per model** — burning requests across multiple model names during testing exhausts the quota fast.

## 8. Fresh install: RocketRide engine won't start

**Symptom:** A clean install of the RocketRide engine fails to start. This is an upstream packaging bug — it will hit every fresh install until RocketRide re-pins the dependency.

**Root cause:** The engine ships pinned to `onnxruntime-gpu==1.20.1`, which no longer exists on PyPI. `pip install` for that pin fails, so the engine process never comes up.

**Fix:** Patch the pin from `1.20.1` to `1.20.2` in the five requirements files under:
```
%LOCALAPPDATA%\RocketRide\engine\
```
(the `whisper`, `gliner`, `pose`, `anonymize`, and `audio_transcribe` requirements files), then delete:
```
%LOCALAPPDATA%\RocketRide\engine\cache\combined.txt
```
so the engine rebuilds its combined dependency cache from the patched files.
