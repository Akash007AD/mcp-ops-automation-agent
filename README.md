# Inbox-to-Action — MCP Automation Agent

An automation agent that watches a team's Slack channel for incoming requests, classifies each one with an LLM, logs it to a tracker, and delivers daily and weekly status summaries to Slack and email — without anyone manually scrolling Slack to write a status update.

## The problem

Small teams field requests scattered across Slack, email, and spreadsheets. Without a system, requests get buried in channel scroll, and someone ends up manually reading through messages every week to compile a status update — typically 30-60 minutes of pure busywork, repeated indefinitely.

## What this does

- **Hourly intake** — reads new messages from a Slack channel, classifies each as `bug`, `feature`, `question`, or `noise`, and logs it to a tracker (Google Sheets or Notion).
- **Daily overview** (6 PM by default) — summarizes the day's new requests and posts the summary to Slack and email.
- **Weekly digest** (Monday 9 AM by default) — summarizes the past 7 days, including resolution rate and recurring themes, posted to Slack and email.
- **Urgency flagging** — requests that describe a genuine outage, active financial loss, or explicit urgency are flagged separately from routine bugs and feature requests.

No custom ML model is involved. All classification and summarization is done by an LLM (Groq) with task-specific prompts.

## Architecture

```
                 Slack Workspace
                 (#requests channel)
                         |
                         | new messages
                         v
              read_messages()  --------->  LLM classifies
                                            (bug/feature/question/noise)
                                                    |
                                                    v
                                         add_entry() -> Tracker
                                       (Google Sheets / Notion)

Trigger schedule:
  Hourly  -> read_messages() -> classify -> add_entry()
  Daily   -> list_open_entries(since=today) -> draft summary
             -> post_message() + send_summary_email()
  Weekly  -> list_open_entries(since=7d_ago) -> draft digest
             -> post_message() + send_summary_email()
```

### Components

| Component | Responsibility |
|---|---|
| `src/core/slack_ops.py` | Slack Web API wrapper — read-only except for posting the agent's own summaries |
| `src/core/tracker.py` | Tracker abstraction with two interchangeable backends (Google Sheets, Notion) |
| `src/core/llm_ops.py` | Groq client + the classification, daily, and weekly prompts |
| `src/core/email_ops.py` | Resend wrapper for outbound summary emails |
| `src/orchestrators/*.py` | The three scheduled jobs (hourly intake, daily overview, weekly digest) |
| `scheduler.py` | Wires the three jobs to their trigger schedule and runs continuously |
| `src/mcp_servers/*.py` | The same tracker, Slack, and email operations exposed as MCP tools — see below |

### Safety boundaries

- The agent is read-only on Slack except for posting its own summary messages. It never edits or deletes other users' messages and never auto-replies to a requester.
- The agent writes to exactly one tracker database, configured at setup time.
- Email recipients are defined in a static `config.yaml`. The agent cannot discover or add new recipients on its own.

## A note on the MCP servers

This project includes three MCP servers (`src/mcp_servers/`) that expose the tracker, Slack, and email operations as tools for an MCP client such as Claude Desktop or Claude Code — for example, asking Claude directly "what's open in the tracker right now?"

These run over **stdio**, which is intentional: each deployment is local and personalized to one organization, not exposed over a network. There is no shared, multi-tenant server — each team runs its own private copy with its own credentials, locked to its own machine. This keeps every organization's Slack tokens, tracker data, and email credentials fully isolated from any other deployment, with no shared infrastructure or external attack surface.

It's worth separating two things this project does:

1. **The automation itself** (`scheduler.py`) — this is what your team actually experiences. It runs as a standalone background process and needs no MCP client at all. Anyone on the team interacts with it purely through Slack and email.
2. **The MCP servers** — an additional, optional interactive layer for whoever is running the deployment, to query or control the system directly through a local AI assistant. Because they're stdio-based, they only work on the same machine where they're configured — there is no remote endpoint to connect to from elsewhere.

If multi-user remote access to the MCP tools were needed in the future, the servers would need to move to an HTTP/SSE transport with proper authentication. That's a deliberate non-goal for this version: the design favors a locked-down, single-organization local deployment over a shared remote one.

## Setup

### Prerequisites

- Python 3.10+
- A Slack workspace where you can create an app/bot
- A Google Cloud service account (for the Sheets tracker) or a Notion integration (for the Notion tracker)
- A [Groq](https://groq.com) API key
- A [Resend](https://resend.com) API key

### 1. Install dependencies

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
copy .env.example .env                  # Windows
# cp .env.example .env                  # macOS/Linux
copy config.example.yaml config.yaml
```

Fill in `.env` with your Slack bot token, Google service account path / Sheet ID (or Notion credentials), Groq API key, and Resend API key. Fill in `config.yaml` with your tracker backend choice and email recipient lists.

`.env`, `config.yaml`, and `service_account.json` are gitignored — never commit real credentials.

### 3. Set up Slack

- Create a Slack app, add a bot user, and install it to your workspace.
- Required bot scopes: `channels:history`, `chat:write` (add `groups:history` if your requests channel is private).
- Invite the bot to your requests channel and your updates channel.

### 4. Set up the tracker

**Google Sheets (default):**
- Create a Sheet with columns: `id, title, category, source_text, status, urgent, created_at`.
- Create a Google Cloud service account, download its JSON key as `service_account.json`, and share the Sheet with the service account's email address (Editor access).

**Notion (alternative):**
- Create a Notion integration and a database with properties: `Title`, `Category`, `Source Text`, `Status`, `Urgent`, `Created At`.
- Share the database with your integration.
- Set `tracker.backend: "notion"` in `config.yaml`.

### 5. Run

```bash
python scheduler.py
```

This runs continuously: hourly intake on the hour, daily overview at the configured time, and weekly digest on the configured day. Each job is independently wrapped in error handling, so a failure in one never stops the others from running on schedule.

To run a single job manually for testing:

```bash
python -m src.orchestrators.hourly_intake
python -m src.orchestrators.daily_overview
python -m src.orchestrators.weekly_digest
```

### 6. (Optional) Use the MCP servers locally

To query the tracker, Slack, or email tools interactively through Claude Desktop or Claude Code, add the servers to your MCP client's config. On Windows, Claude Desktop's config file is at `%APPDATA%\Claude\claude_desktop_config.json`.

Point `command` at the Python interpreter **inside this project's venv**, not a global `python` — Claude Desktop launches these as subprocesses without the venv activated, so a global interpreter won't have `mcp`, `slack_sdk`, `gspread`, etc. installed. Example (adjust the path to wherever you cloned the project):

```json
{
  "mcpServers": {
    "tracker-tools": {
      "command": "D:\\MCP_Automation\\venv\\Scripts\\python.exe",
      "args": ["D:\\MCP_Automation\\src\\mcp_servers\\tracker_server.py"]
    },
    "slack-tools": {
      "command": "D:\\MCP_Automation\\venv\\Scripts\\python.exe",
      "args": ["D:\\MCP_Automation\\src\\mcp_servers\\slack_server.py"]
    },
    "email-tools": {
      "command": "D:\\MCP_Automation\\venv\\Scripts\\python.exe",
      "args": ["D:\\MCP_Automation\\src\\mcp_servers\\email_server.py"]
    }
  }
}
```

On macOS/Linux, point `command` at `venv/bin/python` instead, using forward slashes.

No `cwd` is needed — each server script resolves the project root itself (`sys.path.insert(0, ...parents[2])`), and configuration is loaded relative to that root, so credentials in `.env`/`config.yaml` are found regardless of where the process is launched from.

After saving the config, fully quit and reopen Claude Desktop (not just close the window) for it to pick up the new servers. This only works locally, on the machine where the project and its credentials are set up — see the note above.

## Testing the pipeline end to end

A seed script is included to push a realistic batch of test messages through the full pipeline (classification, tracker logging, daily/weekly summaries) without manually typing into Slack:

```bash
python scripts/seed_test_messages.py
python -m src.orchestrators.daily_overview
python -m src.orchestrators.weekly_digest
```

It includes a duplicate guard, so re-running it skips any message already logged. To reset the tracker to a clean state first:

```bash
python scripts/clear_tracker.py
```

This is a destructive operation and requires typing `yes` to confirm.

## Stack

- **Language:** Python
- **MCP SDK:** official `mcp` Python SDK
- **LLM:** Groq (Llama 3.3 70B) for classification and summarization
- **Slack:** Slack Web API
- **Tracker:** Google Sheets API (`gspread`), with a Notion backend available behind the same interface
- **Email:** Resend
- **Scheduling:** `schedule` Python library

## What's next

- Multi-channel support (triage across several Slack channels)
- Per-user email preferences (opt-in/out of daily vs. weekly digest)
- HTML-formatted emails with color-coded categories
- Basic access control for marking items resolved
- HTTP/SSE transport for the MCP servers, if multi-user remote access becomes a requirement
