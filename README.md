# Inbox-to-Action 🤖

An MCP-powered automation agent that watches Slack channels, classifies messages using Groq (LLaMA 3.3-70B), logs them to Google Sheets (or Notion), and sends daily/weekly summaries via Slack, Email, and Telegram. Urgent items trigger an immediate Telegram alert. Also exposes standalone Notion and Google Calendar tools.

## Architecture

```
Slack (multiple intake channels)
      ↓
 Hourly Intake Orchestrator
      ↓
 Groq LLaMA 3.3-70B  →  classify (bug / feature / question / noise) + urgent flag
      ↓
 Tracker (Google Sheets or Notion)  →  log entry
      ↓                                    ↓ (if urgent)
 Daily / Weekly Orchestrator          Telegram alert (immediate)
      ↓
 Slack post  +  Email (SMTP)  +  Telegram
```

## MCP Servers

**Use `unified_server.py` — this is the only server actually wired into Claude
Desktop in this project** (see the `claude_desktop_config.json` snippet in
[Usage](#usage) below). It exposes all 16 tools across Slack, tracker, email,
Notion, Calendar, and Telegram from a single process.

| Server | Tools |
|---|---|
| `mcp-automation` (unified — `unified_server.py`) ✅ **active** | Slack: `read_messages`, `post_message`, `list_channels` · Tracker: `add_entry`, `list_open_entries`, `update_status` · Email: `send_summary_email` · Notion: `notion_create_page`, `notion_query_database`, `notion_update_page` · Calendar: `calendar_create_event`, `calendar_list_events` · Telegram: `telegram_send_message`, `telegram_send_to_group` |

<details>
<summary>Legacy / optional: three single-purpose servers (not currently wired up)</summary>

These still work standalone if you'd rather run a smaller process per
integration, but they only cover Slack, tracker, and email — no
Notion/Calendar/Telegram. They're kept in the codebase for that use case,
not because the unified server is missing anything.

| Server | Tools |
|---|---|
| `slack-tools` | `read_messages`, `post_message`, `list_channels`, `create_channel`, `remove_channel_tool`, `list_intake_channels`, `sync_channels` |
| `tracker-tools` | `add_entry`, `list_open_entries`, `update_status` |
| `email-tools` | `send_summary_email` |

</details>

## Setup

### 1. Clone & install
```bash
git clone https://github.com/your-username/inbox-to-action.git
cd inbox-to-action
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. Configure secrets
```bash
copy .env.example .env
# Fill in your API keys in .env
```

### 3. Configure settings
```bash
copy config.example.yaml config.yaml
# Edit config.yaml with your channel names and email recipients
```

### 4. Add Google service account
- Create a service account at [console.cloud.google.com](https://console.cloud.google.com)
- Enable Google Sheets API + Google Drive API
- Download the JSON key → save as `service_account.json` in project root
- Share your Google Sheet with the service account email as Editor

### 5. API Keys needed

| Service | Where to get it |
|---|---|
| Groq | [console.groq.com](https://console.groq.com) → API Keys |
| Slack Bot Token | [api.slack.com/apps](https://api.slack.com/apps) → OAuth & Permissions |
| Google Sheets | Service account JSON (see above) |
| SMTP (email) | Gmail App Password — myaccount.google.com → Security → App Passwords (or any other SMTP provider) |
| Telegram | [@BotFather](https://t.me/botfather) → /newbot |
| Notion *(optional)* | [notion.so/my-integrations](https://notion.so/my-integrations) — needed only if using the Notion tracker backend or the standalone Notion tools |
| Google Calendar *(optional)* | Uses the same service account as Google Sheets — share your calendar with the service account's `client_email` |

> **Note on urgent alerts:** urgent items today trigger an immediate
> **Telegram** alert only (`hourly_intake.py` → `_send_urgent_alert`). The
> `email.recipients.alerts` list in `config.yaml` is defined but not called
> automatically by any orchestrator — wire up `send_alert_email()` in
> `email_ops.py` if you also want urgent items emailed.

### 6. Slack Bot Scopes required
```
channels:history   channels:read   channels:manage
channels:join      chat:write      groups:history   groups:read
```

## Usage

### Run the pipeline manually
```bash
# Process new Slack messages
python -m src.orchestrators.hourly_intake

# Send daily summary (Slack + Email + Telegram)
python -m src.orchestrators.daily_overview

# Send weekly digest (Slack + Email + Telegram)
python -m src.orchestrators.weekly_digest
```

### Or run everything on schedule
```bash
python scheduler.py
```
Runs hourly intake every hour, daily overview at the configured time
(default 18:00), and the weekly digest on the configured weekday
(default Monday 09:00). See `.env` for `DAILY_SUMMARY_TIME`,
`WEEKLY_SUMMARY_DAY`, `WEEKLY_SUMMARY_TIME`.

### Manage Slack channels
```bash
# Create a new channel and auto-register it for intake
python -m src.utils.channel_manager create feature-requests

# List all registered intake channels
python -m src.utils.channel_manager list

# Remove a channel (archives in Slack + unregisters from config.yaml)
python -m src.utils.channel_manager remove feature-requests

# Sync config.yaml with Slack (auto-join missing channels)
python -m src.utils.channel_manager sync
```

### Wire into Claude Desktop
**This is the config actually in use for this project.** Add to
`claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "mcp-automation": {
      "command": "python",
      "args": ["D:/MCP_Automation/src/mcp_servers/unified_server.py"]
    }
  }
}
```
This single entry exposes all 16 tools (Slack, tracker, email, Notion,
Calendar, Telegram).

<details>
<summary>Legacy / optional: three smaller single-purpose servers instead</summary>

Not used in this project's actual setup, but still work if you'd rather run
a smaller process per integration. Covers only Slack, tracker, and email —
no Notion/Calendar/Telegram:
```json
{
  "mcpServers": {
    "slack-tools": {
      "command": "python",
      "args": ["D:/MCP_Automation/src/mcp_servers/slack_server.py"]
    },
    "tracker-tools": {
      "command": "python",
      "args": ["D:/MCP_Automation/src/mcp_servers/tracker_server.py"]
    },
    "email-tools": {
      "command": "python",
      "args": ["D:/MCP_Automation/src/mcp_servers/email_server.py"]
    }
  }
}
```

</details>

## Schedule with Windows Task Scheduler

The simplest option is to schedule `scheduler.py` itself once — it runs all
three jobs (hourly intake, daily overview, weekly digest) internally on
the timings from `.env`:
```
Program: D:\MCP_Automation\venv\Scripts\python.exe
Arguments: scheduler.py
Start in: D:\MCP_Automation
Trigger: At startup / At log on (it then runs continuously)
```

Alternatively, schedule each job as its own separate Task Scheduler entry:

Hourly intake every hour:
```
Program: D:\MCP_Automation\venv\Scripts\python.exe
Arguments: -m src.orchestrators.hourly_intake
Start in: D:\MCP_Automation
```

Daily overview at 6 PM:
```
Program: D:\MCP_Automation\venv\Scripts\python.exe
Arguments: -m src.orchestrators.daily_overview
Trigger: Daily at 18:00
Start in: D:\MCP_Automation
```

Weekly digest Monday at 9 AM:
```
Program: D:\MCP_Automation\venv\Scripts\python.exe
Arguments: -m src.orchestrators.weekly_digest
Trigger: Weekly, Monday at 09:00
Start in: D:\MCP_Automation
```

## Project Structure

```
MCP_Automation/
├── src/
│   ├── core/
│   │   ├── config.py          # Central settings loader
│   │   ├── slack_ops.py       # Slack Web API wrapper
│   │   ├── llm_ops.py         # Groq classification + summary drafting
│   │   ├── email_ops.py       # SMTP email sender
│   │   ├── tracker.py         # Google Sheets / Notion tracker (swappable)
│   │   ├── notion_ops.py      # Standalone Notion workspace tools
│   │   ├── calendar_ops.py    # Google Calendar tools
│   │   ├── telegram_ops.py    # Telegram bot messaging
│   │   └── state.py           # Run state persistence (intake cursor)
│   ├── mcp_servers/
│   │   ├── unified_server.py  # MCP: mcp-automation (all 16 tools — recommended)
│   │   ├── slack_server.py    # MCP: slack-tools (standalone)
│   │   ├── tracker_server.py  # MCP: tracker-tools (standalone)
│   │   └── email_server.py    # MCP: email-tools (standalone)
│   ├── orchestrators/
│   │   ├── hourly_intake.py   # Hourly pipeline runner + urgent Telegram alert
│   │   ├── daily_overview.py  # Daily summary → Slack + Email + Telegram
│   │   └── weekly_digest.py   # Weekly digest → Slack + Email + Telegram
│   └── utils/
│       ├── channel_manager.py # Slack channel lifecycle manager
│       └── logging_setup.py   # Rotating file + console logger
├── scripts/
│   ├── seed_test_messages.py # Seeds 20 realistic test messages end-to-end
│   ├── check_urgency.py      # Regression check for the urgency classifier
│   └── clear_tracker.py      # Destructive admin script — wipes the tracker
├── scheduler.py             # Runs all three jobs on schedule, in one process
├── .env.example             # Secret keys template
├── config.example.yaml      # Settings template
├── requirements.txt
└── README.md
```

## Built With

- [Groq](https://groq.com) — LLaMA 3.3-70B for message classification and summary drafting
- [Slack SDK](https://slack.dev/python-slack-sdk/) — Slack Web API
- [FastMCP](https://github.com/jlowin/fastmcp) — MCP server framework
- [gspread](https://docs.gspread.org/) — Google Sheets tracker backend
- [notion-client](https://github.com/ramnes/notion-sdk-py) — Notion tracker backend + standalone Notion tools
- [google-api-python-client](https://github.com/googleapis/google-api-python-client) — Google Calendar
- SMTP (`smtplib`, standard library) — email delivery, no third-party email account needed
- [httpx](https://www.python-httpx.org/) — Telegram Bot API client
- `schedule` — job scheduling
