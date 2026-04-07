"""SQLite-backed conversation persistence.

Stores per-agent, per-user message history that survives bot restarts.

The tricky part is serialization: conversation history contains a mix of
plain strings (user messages), tool-result dicts (tool responses), and
Pydantic ContentBlock objects (from the Anthropic SDK). The serializer
handles all three without losing type information that Claude needs on
the next turn.
"""

import json
import os
import sqlite3
import logging

log = logging.getLogger("agenthub.history")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "conversations.db")

_conn = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                agent TEXT NOT NULL,
                author TEXT NOT NULL,
                messages TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (agent, author)
            )
        """)
        _conn.commit()
        log.info(f"Conversation store opened: {DB_PATH}")
    return _conn


def _serialize_message(msg: dict) -> dict:
    """Convert a message dict to a JSON-safe form.

    The 'content' field can be:
    - A plain string (user messages, simple assistant replies)
    - A list of tool_result dicts (tool responses)
    - A list of Pydantic ContentBlock objects (from anthropic SDK)
    """
    role = msg.get("role", "")
    content = msg.get("content", "")

    if isinstance(content, str):
        return {"role": role, "content": content}

    if isinstance(content, list):
        safe_blocks = []
        for block in content:
            if isinstance(block, dict):
                safe_blocks.append(block)
            elif hasattr(block, "model_dump"):
                # Pydantic model from anthropic SDK
                safe_blocks.append(block.model_dump())
            elif hasattr(block, "text"):
                safe_blocks.append({"type": "text", "text": block.text})
            else:
                safe_blocks.append({"type": "text", "text": str(block)})
        return {"role": role, "content": safe_blocks}

    return {"role": role, "content": str(content)}


def load_history(agent_name: str, author: str, max_messages: int = 40) -> list[dict]:
    """Load conversation history for an agent+author pair."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT messages FROM history WHERE agent = ? AND author = ?",
        (agent_name, author),
    ).fetchone()

    if row is None:
        return []

    try:
        messages = json.loads(row[0])
        if len(messages) > max_messages:
            messages = messages[-max_messages:]
        return messages
    except (json.JSONDecodeError, TypeError):
        return []


def save_history(agent_name: str, author: str, messages: list[dict], max_messages: int = 40):
    """Save conversation history, trimming to max_messages."""
    safe = [_serialize_message(m) for m in messages]
    if len(safe) > max_messages:
        safe = safe[-max_messages:]

    conn = _get_conn()
    conn.execute(
        """INSERT INTO history (agent, author, messages, updated_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(agent, author) DO UPDATE SET
               messages = excluded.messages,
               updated_at = excluded.updated_at""",
        (agent_name, author, json.dumps(safe)),
    )
    conn.commit()


def clear_history(agent_name: str, author: str = None):
    """Clear history for an agent, optionally scoped to one author."""
    conn = _get_conn()
    if author:
        conn.execute(
            "DELETE FROM history WHERE agent = ? AND author = ?",
            (agent_name, author),
        )
    else:
        conn.execute("DELETE FROM history WHERE agent = ?", (agent_name,))
    conn.commit()
