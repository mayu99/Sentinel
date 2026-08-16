# Sentinel — data-pipeline incident triage on RocketRide

When a dbt or Airflow job fails at 3am, an on-call data engineer spends 30–60 minutes grepping logs, checking whether an upstream table changed, and writing up an incident. Sentinel does that automatically. It receives the failure event, inspects the **live warehouse schema** to find the root cause, writes an incident report, and posts a summary to Slack — all as **RocketRide pipelines**.

Built by [Mayuresh Pandey](https://github.com/mayu99) · previous RocketRide build: [Loop](https://github.com/mayu99/Loop) (HackWithBay3)

## Why RocketRide is the right runtime for this

- **Self-host is not optional for this problem.** Warehouse credentials and raw production logs cannot leave the network at most data teams. Sentinel runs on RocketRide's local runtime with `llm_ollama` (Llama 3.1 8B) as the default brain — zero bytes to a hosted LLM. Swap one node for `llm_anthropic`/`llm_openai` if your policy allows.
- **The node graph is the architecture doc.** Both pipelines are portable JSON `.pipe` files — open them in the RocketRide VS Code canvas and the whole system is legible in one screen.
- **Observability debugging observability.** Every triage run is traced node-by-node in the RocketRide dashboard, so you can watch the agent parse the failure, call `postgres.get_schema`, and converge on the root cause — the incident *investigation* is itself fully auditable.

## Architecture

Two pipelines, mirroring a reactive/reflective split:

**`pipelines/sentinel-triage.pipe`** — event-driven

```
webhook (dbt/Airflow failure event)
   └─ questions ─▶ Sentinel Triage Agent ─ answers ─▶ response
                     │ llm      Ollama (local, Llama 3.1 8B)
                     │ memory   Memory (Internal)
                     │ tool     Warehouse (db_postgres → get_schema / get_data)
                     │ tool     Python Sandbox (tool_python → drift diffing)
                     │ tool     Incident Store (tool_filesystem → incidents/*.md)
                     │ tool     Slack (tool_slack → #data-incidents, optional)
```

The agent follows a strict triage protocol: parse the failure → fetch the *current* schema of the upstream tables → diagnose drift (every column claim must come from `postgres.get_schema`, never from the payload alone) → propose the minimal SQL fix plus one guardrail → persist the report → notify Slack.

**`pipelines/sentinel-postmortem.pipe`** — on-demand

```
chat ─ questions ─▶ Sentinel Postmortem Agent ─ answers ─▶ response
                      │ llm     Ollama (local)
                      │ tool    Incident Store (reads incidents/*.md)
```

Ask it "digest of this week's incidents" and it synthesizes recurring root-cause patterns and the single highest-leverage preventive action from the reports the triage agent wrote.

## Quickstart (demo)

The demo ships a realistic broken state: an upstream team renamed `public.customers.customer_email` → `email`, and the dbt staging model was never updated. Sentinel discovers this by inspecting the live schema — it is not told the answer.

1. **Start the demo warehouse** (Postgres 16 with the drifted schema pre-seeded):
   ```bash
   cd demo && docker compose up -d
   ```
2. **Start a local model**: `ollama pull llama3.1:8b` (Ollama serving on `localhost:11434`).
3. **Configure env**: `cp .env.example .env` and export, or set the variables in RocketRide's environment config. Slack token is optional — without it the agent skips the notify step.
4. **Open and run the pipelines**: load `pipelines/sentinel-triage.pipe` in the RocketRide VS Code extension and start it. The Project Log prints the webhook URL.
5. **Fire the failure**:
   ```bash
   export SENTINEL_WEBHOOK_URL=<webhook_url_from_project_log>
   export SENTINEL_API_KEY=<your RocketRide API key>
   python scripts/fire_failure.py
   ```
6. **Watch the dashboard**: the trace shows the agent reading the payload, calling `postgres.get_schema('public.customers')`, spotting that `customer_email` no longer exists (and that `email` does), and emitting the fix. The incident report lands in the file store under `incidents/`, and — with a token configured — a summary lands in `#data-incidents`.
7. **Run the postmortem**: start `pipelines/sentinel-postmortem.pipe`, open its chat URL, and ask for a digest.

Expected root cause, for reference: *"Upstream table `public.customers` renamed `customer_email` to `email`; `stg_customers.sql` still selects `customer_email`, failing the view build and skipping downstream `fct_orders`."* The fix is a one-line model change plus a dbt source contract/test to catch the next rename before the nightly run does.

## Repo layout

```
pipelines/   Two RocketRide .pipe files (the whole system)
demo/        docker-compose Postgres warehouse, seed.sql with the drifted
             schema, the broken dbt project, and the failure payload
scripts/     fire_failure.py — replays the dbt failure event at the webhook
```

## Real-world extension points

- Point the webhook at dbt Cloud webhooks or an Airflow `on_failure_callback` instead of the replay script.
- Swap `db_postgres` for RocketRide's `db_clickhouse`/`db_mysql` nodes to match your warehouse.
- Add a second source lane for Airflow task-level failures (timeouts, OOM) alongside dbt model failures.
