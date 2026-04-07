"""Channel-to-agent dispatcher — excerpt from bot.py.

Messages are routed by channel ID, not by command prefix or message
content. Each Discord channel maps to exactly one agent. The mapping
is config-driven — the !setup command links any channel to any agent
at runtime.

This also shows:
- Message splitting for Discord's 2000-char limit
- Cross-agent wiring (Gmail -> Job Hunter for job email grading)
- The general-channel fallback router
"""

import discord
from discord.ext import commands

# --- Agent registry (populated on startup) ---

agents = {}


def get_agent_for_channel(channel_id: int) -> str | None:
    """Look up which agent handles a given channel ID."""
    config = load_config()
    channel_map = config.get("discord", {}).get("channels", {})
    for agent_name, cid in channel_map.items():
        if cid == channel_id:
            return agent_name
    return None


# --- Message routing ---

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    agent_name = get_agent_for_channel(message.channel.id)

    if agent_name and agent_name in agents:
        async with message.channel.typing():
            try:
                response = await agents[agent_name].handle_message(
                    user_message=message.content,
                    author=str(message.author),
                    channel=message.channel.name,
                    attachments=[a.url for a in message.attachments],
                )
                for chunk in split_message(response):
                    await message.channel.send(chunk)

            except Exception as e:
                log.error(f"Agent '{agent_name}' error: {e}", exc_info=True)
                await message.channel.send(
                    f"Something went wrong with the {agent_name} agent. Check the logs."
                )

    elif agent_name == "general":
        async with message.channel.typing():
            response = await handle_general_message(message)
            for chunk in split_message(response):
                await message.channel.send(chunk)

    await bot.process_commands(message)


# --- Cross-agent wiring (done at startup) ---

async def load_agents():
    """Import and initialize all agent modules."""
    global agents

    # ... (each agent loaded in try/except for independent failure) ...

    # Wire cross-agent connections
    if "gmail" in agents and "job_hunter" in agents:
        agents["gmail"]._job_hunter = agents["job_hunter"]
        # Link the job hunter Discord channel so Gmail can post grades there
        config = load_config()
        job_channel_id = config.get("discord", {}).get("channels", {}).get("job_hunter")
        if job_channel_id:
            agents["gmail"]._job_channel = bot.get_channel(job_channel_id)
        log.info("  Wired: Gmail -> Job Hunter (job email auto-grading)")


# --- Message splitting for Discord's 2000-char limit ---

def split_message(text: str, limit: int = 2000) -> list[str]:
    """Split a message into chunks that fit Discord's character limit."""
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break

        # Try to split at a newline for cleaner output
        split_pos = text.rfind("\n", 0, limit)
        if split_pos == -1:
            split_pos = limit

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")

    return chunks
