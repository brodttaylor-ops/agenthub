"""Process-level locking and host guard — excerpt from bot.py.

The bot runs on an always-on ThinkPad with auto-start via Windows Task
Scheduler. Two problems to solve:

1. Duplicate instances: OneDrive syncs the project folder between
   machines. Task Scheduler fires on boot. Without a guard, both
   machines could try to run the bot.

2. Stale lock files: A simple PID file breaks if the bot crashes without
   cleanup. Instead, we scan all running Python processes for other
   bot.py instances — a live process check, not a file check.

The hostname guard is the first line of defense (only the ThinkPad's
hostname is whitelisted). The process scan is the second.
"""

import os
import sys
import socket

# --- Machine guard: only the dedicated server may run the bot ---

_ALLOWED_HOST = "BRODT"

if socket.gethostname().upper() != _ALLOWED_HOST:
    print(
        f"[AgentHub] This bot is only permitted to run on ({_ALLOWED_HOST}).\n"
        f"  Current host: {socket.gethostname()}\n"
        "  Exiting."
    )
    sys.exit(0)


# --- Process-level lock: scan for other running instances ---

LOCK_FILE = os.path.join(os.path.dirname(__file__), "bot.lock")


def _acquire_lock():
    """Prevent multiple bot instances from running simultaneously.

    Scans ALL running Python processes for 'bot.py' in the command line,
    not just the PID in the lock file. This catches cases where the lock
    file was left behind after a crash.
    """
    import psutil

    my_pid = os.getpid()

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] == my_pid:
                continue
            if proc.info["name"] and "python" in proc.info["name"].lower():
                cmdline = " ".join(proc.info["cmdline"] or [])
                if "bot.py" in cmdline:
                    print(
                        f"ERROR: Bot already running (PID {proc.info['pid']}). "
                        "Kill it first or delete bot.lock."
                    )
                    sys.exit(1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    with open(LOCK_FILE, "w") as f:
        f.write(str(my_pid))


def _release_lock():
    """Remove lock file on shutdown."""
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass


# --- Usage in main() ---

def main():
    _acquire_lock()
    import atexit
    atexit.register(_release_lock)

    # ... bot startup ...
    bot.run(token)
