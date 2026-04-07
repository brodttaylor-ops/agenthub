"""Independent proactive notification loops — excerpt from bot.py.

Each agent has its own proactive loop with independent timing and a
120-second timeout. A hung Gmail API call doesn't block the Job Hunter's
scheduled run.

This replaced an earlier design where all agents shared a single
sequential loop — one slow agent would delay all the others.
"""

import asyncio
from discord.ext import tasks

PROACTIVE_TIMEOUT = 120  # seconds


async def _check_agent(agent_name: str, agent):
    """Run one agent's proactive check with a timeout."""
    config = load_config()
    if not config.get("notifications", {}).get(f"{agent_name}_proactive", False):
        return

    channel_id = config.get("discord", {}).get("channels", {}).get(agent_name)
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        return

    try:
        notifications = await asyncio.wait_for(
            agent.check_notifications(), timeout=PROACTIVE_TIMEOUT
        )
        for note in notifications:
            for chunk in split_message(note):
                await channel.send(chunk)
    except NotImplementedError:
        pass
    except asyncio.TimeoutError:
        log.error(f"Proactive check timed out for {agent_name}")
        await channel.send(
            f"**{agent_name}:** proactive check timed out after {PROACTIVE_TIMEOUT}s"
        )
    except Exception as e:
        log.error(f"Proactive check failed for {agent_name}: {e}")
        await channel.send(f"**{agent_name} error:** {str(e)[:500]}")


# Each agent gets its own loop — independent timing, independent failures

@tasks.loop(minutes=5)
async def gmail_proactive_loop():
    """Gmail agent — poll every 5 minutes."""
    if "gmail" in agents:
        await _check_agent("gmail", agents["gmail"])


@tasks.loop(minutes=5)
async def job_hunter_proactive_loop():
    """Job Hunter — check for scheduled runs every 5 minutes.
    The agent internally checks if today is M/W/F and if it's past 7 AM."""
    if "job_hunter" in agents:
        await _check_agent("job_hunter", agents["job_hunter"])


@tasks.loop(minutes=5)
async def syc_proactive_loop():
    """SYC agent — check for daily run every 5 minutes.
    The agent internally checks if it's past noon."""
    if "syc" in agents:
        await _check_agent("syc", agents["syc"])
