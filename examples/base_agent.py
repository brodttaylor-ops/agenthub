"""Base class for all AgentHub agents.

All five agents inherit from this. Handles:
- Multi-round tool-use loops (Claude calls a tool, gets the result,
  decides whether to call another)
- Per-user conversation history with automatic SQLite persistence
- Configurable tool definitions (subclasses define tools + execute_tool())
- Safety limits on tool-use rounds to prevent runaway loops
"""

from tracked_client import TrackedClient
from history_store import load_history, save_history, clear_history as _clear_stored


class BaseAgent:
    """Common interface for all agents."""

    # Subclasses set this for history keying (e.g., "gmail", "job_hunter")
    agent_name: str = "base"

    def __init__(self, model: str = "claude-sonnet-4-6", system_prompt: str = ""):
        self.model = model
        self.system_prompt = system_prompt
        self.client = TrackedClient()
        self.conversations: dict[str, list[dict]] = {}  # per-user history
        self.max_history = 20
        self.tools: list[dict] | None = None  # override in subclass
        self.max_tool_rounds = 5

    def _get_history(self, author: str) -> list[dict]:
        """Get conversation history, loading from SQLite if not in memory."""
        if author not in self.conversations:
            stored = load_history(self.agent_name, author, self.max_history * 2)
            self.conversations[author] = stored
        return self.conversations[author]

    def _save_history(self, author: str):
        """Persist current conversation history to SQLite."""
        history = self.conversations.get(author, [])
        save_history(self.agent_name, author, history, self.max_history * 2)

    async def handle_message(
        self,
        user_message: str,
        author: str = "user",
        channel: str = "",
        attachments: list[str] | None = None,
    ) -> str:
        """Handle an incoming message and return a response."""
        content = user_message
        if attachments:
            content += "\n\n[Attachments: " + ", ".join(attachments) + "]"

        history = self._get_history(author)
        history.append({"role": "user", "content": content})

        # Trim history
        if len(history) > self.max_history * 2:
            history[:] = history[-(self.max_history * 2):]

        api_kwargs = {
            "model": self.model,
            "max_tokens": 2000,
            "system": self.system_prompt,
            "messages": history,
        }
        if self.tools:
            api_kwargs["tools"] = self.tools

        # Tool-use loop: Claude may call tools and then decide to call more
        response = self.client.messages.create(**api_kwargs)
        rounds = 0

        while response.stop_reason == "tool_use" and rounds < self.max_tool_rounds:
            rounds += 1

            tool_results = []
            assistant_content = response.content

            for block in assistant_content:
                if block.type == "tool_use":
                    result = await self.execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })

            # Add assistant response + tool results to history
            history.append({"role": "assistant", "content": assistant_content})
            history.append({"role": "user", "content": tool_results})

            response = self.client.messages.create(**api_kwargs)

        # Extract final text
        reply = ""
        for block in response.content:
            if hasattr(block, "text"):
                reply += block.text

        history.append({"role": "assistant", "content": reply})
        self._save_history(author)

        return reply

    async def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call. Override in subclasses."""
        return f"Tool '{tool_name}' not implemented."

    async def check_notifications(self) -> list[str]:
        """Check for proactive notifications. Override in subclasses."""
        raise NotImplementedError

    def clear_history(self, author: str = None):
        """Clear conversation history (memory + SQLite)."""
        if author:
            self.conversations.pop(author, None)
            _clear_stored(self.agent_name, author)
        else:
            self.conversations.clear()
            _clear_stored(self.agent_name)
