"""
LLM operations — Groq client + the three prompts from 05_SYSTEM_PROMPTS.md
(classification, daily overview, weekly digest).

Treat 05_SYSTEM_PROMPTS.md as the source of truth: if you tune a prompt,
update it there too and bump the version per that file's log table.
"""

from __future__ import annotations

import json
from typing import Optional

from src.core.config import settings

_client = None

CLASSIFICATION_PROMPT = """You are a request triage agent for a small startup team.

You will be given a raw Slack message. Your job is to:
1. Classify it into exactly one of these categories:
   - bug          (something is broken or not working as expected)
   - feature      (a request for new functionality or improvement)
   - question     (asking for information or clarification)
   - noise        (off-topic, social, spam, or not actionable)
2. Write a short title (max 8 words) summarising the request.
3. Flag it as urgent (true/false). Mark urgent=true ONLY when the message
   describes something severe and time-critical RIGHT NOW — a near-total
   outage, a security or data-loss issue, money actively being lost, or it
   explicitly says "urgent", "critical", "emergency", "asap", or "down".
   A bug that is merely annoying, cosmetic, slow, partially broken, or
   affects a single user/feature is NOT urgent — default to urgent=false
   for ordinary bugs. When in doubt, choose false.

   Examples:
     - "export to CSV button does nothing" -> urgent=false (annoying, not blocking)
     - "notifications arrive 10 minutes late" -> urgent=false (degraded, not down)
     - "search bar crashes on emoji input" -> urgent=false (edge case, not blocking)
     - "payment processing is down, losing live transactions" -> urgent=true (active financial loss)
     - "login is broken for half our users, nobody can get in" -> urgent=true (near-total outage)

Respond ONLY in this JSON format, nothing else:
{
  "category": "<bug|feature|question|noise>",
  "title": "<short title>",
  "urgent": <true|false>
}

If the message is noise, still return valid JSON with category "noise"
and a generic title like "Off-topic message"."""

DAILY_OVERVIEW_PROMPT = """You are a team ops assistant generating a daily summary for a small startup.

You will be given a list of requests logged today in JSON format. Each entry
has: title, category, status, created_at.

Write a concise daily overview with this structure:
- One-line headline: total requests today and quick breakdown by category.
- A short bullet list of each request (title + category). Mark urgent ones
  with \U0001F534.
- One closing line: how many are still open vs resolved.

Keep the tone professional but human — this goes to a manager and HR.
Do not invent information not present in the data.
If there are zero entries today, write: "No new requests logged today."

Output plain text only (no markdown headers, no JSON).
Maximum length: 200 words."""

WEEKLY_DIGEST_PROMPT = """You are a team ops assistant generating a weekly digest for a small startup.

You will be given all requests logged in the past 7 days in JSON format.
Each entry has: title, category, status, created_at.

Write a weekly digest with this structure:
1. Headline: total requests this week, breakdown by category (e.g. "12
   requests — 4 bugs, 5 features, 3 questions").
2. Key highlights: call out any urgent items or recurring themes (e.g.
   "3 separate messages mentioned the login page being slow").
3. Status snapshot: how many are open vs resolved this week.
4. One optional sentence on trend: is volume up or down compared to a
   typical week? (Only include if the data clearly supports it — don't
   speculate.)

Keep the tone professional and concise. This goes to managers and HR.
Do not invent information not present in the data.
If there are zero entries this week, write: "No requests logged this week."

Output plain text only (no markdown headers, no JSON).
Maximum length: 300 words."""


def _get_client():
    global _client
    if _client is None:
        from groq import Groq

        settings.validate_for("groq")
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def _chat(system_prompt: str, user_message: str, json_mode: bool = False) -> str:
    client = _get_client()
    kwargs = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.2,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def classify_message(text: str) -> dict:
    """Classify a raw Slack message into {category, title, urgent}.

    Falls back to a safe default (category="noise") if the model returns
    malformed JSON, so a single bad classification never crashes the
    hourly intake loop.
    """
    raw = _chat(CLASSIFICATION_PROMPT, text, json_mode=True)
    try:
        data = json.loads(raw)
        category = str(data["category"]).lower().strip()
        title = str(data["title"]).strip()[:80]
        urgent = bool(data["urgent"])
        if category not in {"bug", "feature", "question", "noise"}:
            raise ValueError(f"unexpected category '{category}'")
        return {"category": category, "title": title, "urgent": urgent}
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        return {
            "category": "noise",
            "title": "Unclassified message (parse error)",
            "urgent": False,
            "_error": str(exc),
            "_raw_response": raw,
        }


def draft_daily_overview(entries: list[dict]) -> str:
    """Draft the daily Slack/email summary from today's logged entries."""
    payload = json.dumps(
        [
            {
                "title": e["title"],
                "category": e["category"],
                "status": e["status"],
                "created_at": e["created_at"],
            }
            for e in entries
        ],
        indent=2,
    )
    return _chat(DAILY_OVERVIEW_PROMPT, payload).strip()


def draft_weekly_digest(entries: list[dict]) -> str:
    """Draft the weekly Slack/email digest from the past 7 days of entries."""
    payload = json.dumps(
        [
            {
                "title": e["title"],
                "category": e["category"],
                "status": e["status"],
                "created_at": e["created_at"],
            }
            for e in entries
        ],
        indent=2,
    )
    return _chat(WEEKLY_DIGEST_PROMPT, payload).strip()
