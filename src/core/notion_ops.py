"""
Notion operations — general-purpose Notion workspace tools.

This is separate from the NotionTracker in tracker.py which is the
swappable tracker backend. This module exposes Notion as a standalone
integration — create/query/update any database or page — so Claude can use
Notion as a knowledge base, project wiki, CRM, or anything else.

Requires:
  NOTION_API_KEY  in .env   (from notion.so/my-integrations)
  Share the target database/page with your integration inside Notion.

Install: pip install notion-client
"""

from __future__ import annotations

from typing import Optional

from src.core.config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        from notion_client import Client

        settings.validate_for("notion")
        _client = Client(auth=settings.notion_api_key)
    return _client


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_title(props: dict) -> str:
    """Pull plain text from whichever property is the title type."""
    for prop in props.values():
        if prop.get("type") == "title":
            items = prop.get("title", [])
            return items[0]["plain_text"] if items else ""
    return ""


def _simplify_page(page: dict) -> dict:
    """Strip Notion's verbose property wrapper to a compact dict."""
    props = page.get("properties", {})
    simplified: dict = {}
    for name, prop in props.items():
        ptype = prop.get("type", "")
        if ptype == "title":
            simplified[name] = _extract_title({name: prop})
        elif ptype == "rich_text":
            items = prop.get("rich_text", [])
            simplified[name] = items[0]["plain_text"] if items else ""
        elif ptype == "select":
            sel = prop.get("select")
            simplified[name] = sel["name"] if sel else ""
        elif ptype == "multi_select":
            simplified[name] = [s["name"] for s in prop.get("multi_select", [])]
        elif ptype == "checkbox":
            simplified[name] = prop.get("checkbox", False)
        elif ptype == "date":
            d = prop.get("date")
            simplified[name] = d["start"] if d else ""
        elif ptype == "number":
            simplified[name] = prop.get("number")
        elif ptype == "url":
            simplified[name] = prop.get("url", "")
        elif ptype == "email":
            simplified[name] = prop.get("email", "")
        elif ptype == "phone_number":
            simplified[name] = prop.get("phone_number", "")
        elif ptype == "status":
            st = prop.get("status")
            simplified[name] = st["name"] if st else ""
        else:
            simplified[name] = f"<{ptype}>"

    return {
        "id": page["id"],
        "url": page.get("url", ""),
        "created_time": page.get("created_time", ""),
        "last_edited_time": page.get("last_edited_time", ""),
        "properties": simplified,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def create_page(
    database_id: str,
    title: str,
    properties: Optional[dict] = None,
    content: Optional[str] = None,
) -> dict:
    """Create a new page in a Notion database.

    Args:
        database_id: target database ID.
        title:       value for the database's Title property.
        properties:  optional additional Notion property payloads to merge in.
                     Must use Notion's raw property format, e.g.:
                     {"Status": {"select": {"name": "In Progress"}}}
        content:     optional plain-text body added as a paragraph block.

    Returns {"id", "url"} of the created page.
    """
    client = _get_client()

    # Build the title property.  We discover the title property name
    # by looking at the database schema so we don't hardcode "Name".
    db = client.databases.retrieve(database_id=database_id)
    title_prop_name = next(
        (k for k, v in db["properties"].items() if v["type"] == "title"),
        "Name",
    )

    merged_props: dict = {
        title_prop_name: {"title": [{"text": {"content": title}}]}
    }
    if properties:
        merged_props.update(properties)

    kwargs: dict = {
        "parent": {"database_id": database_id},
        "properties": merged_props,
    }

    if content:
        kwargs["children"] = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content[:2000]}}]
                },
            }
        ]

    page = client.pages.create(**kwargs)
    return {"id": page["id"], "url": page.get("url", "")}


def query_database(
    database_id: str,
    filter_payload: Optional[dict] = None,
    limit: int = 50,
) -> list[dict]:
    """Query pages from a Notion database with optional filtering.

    Args:
        database_id:    the Notion database ID to query.
        filter_payload: optional Notion filter object, e.g.
                        {"property": "Status", "select": {"equals": "open"}}
        limit:          max pages to return (capped at 100).

    Returns a list of simplified page dicts.
    """
    client = _get_client()
    limit = min(limit, 100)

    results: list[dict] = []
    cursor = None

    while len(results) < limit:
        batch_size = min(100, limit - len(results))
        kwargs: dict = {"database_id": database_id, "page_size": batch_size}
        if filter_payload:
            kwargs["filter"] = filter_payload
        if cursor:
            kwargs["start_cursor"] = cursor

        resp = client.databases.query(**kwargs)
        results.extend(_simplify_page(p) for p in resp["results"])

        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]

    return results


def update_page(page_id: str, properties: dict) -> dict:
    """Update properties on an existing Notion page.

    Args:
        page_id:    the page ID to update.
        properties: Notion property payloads, e.g.
                    {"Status": {"select": {"name": "resolved"}}}

    Returns {"id", "url"} of the updated page.
    """
    client = _get_client()
    page = client.pages.update(page_id=page_id, properties=properties)
    return {"id": page["id"], "url": page.get("url", "")}


def get_page(page_id: str) -> dict:
    """Fetch and simplify a single Notion page by ID."""
    client = _get_client()
    page = client.pages.retrieve(page_id=page_id)
    return _simplify_page(page)
