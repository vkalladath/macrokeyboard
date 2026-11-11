#!/usr/bin/env python3
"""Record every GNOME Settings launch, with the parent process that caused it.

Use this to catch an intermittent "Settings opens by itself" bug. Leave it
running and read the log afterwards:

    ./diagnostics/watch-settings.py
    tail -f ~/.local/state/macropad/settings-launches.log

For each launch it records the timestamp, the command line, and — the part
that actually identifies the culprit — the parent PID and the parent's command
line. If the parent is gnome-shell, the Shell asked for it. If the parent is
systemd --user, it was D-Bus activated and the caller is elsewhere.

Matching is on argv[0] ending in /gnome-control-center. Do NOT use
`pgrep -x gnome-control-center`: the kernel truncates process names to 15
characters ("gnome-control-c"), so exact-name matching never matches.
"""

import glob
import os
import subprocess
import time

STATE = os.path.expanduser("~/.local/state/macropad")
LOG = os.path.join(STATE, "settings-launches.log")
POLL = 0.4


def cmdline_of(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    if not raw:
        return None
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()


def ppid_of(pid):
    try:
        with open(f"/proc/{pid}/stat") as handle:
            raw = handle.read()
        fields = raw[raw.rindex(")") + 2:].split()
        return int(fields[1])
    except (OSError, IndexError, ValueError):
        return None


def settings_pids():
    found = set()
    for path in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError:
            continue
        if not raw:
            continue
        argv0 = raw.split(b"\x00")[0].decode("utf-8", "replace")
        if argv0.endswith("/gnome-control-center"):
            found.add(int(path.split("/")[2]))
    return found


def sink():
    try:
        return subprocess.run(["pactl", "get-default-sink"],
                              capture_output=True, text=True, timeout=2).stdout.strip()
    except Exception:
        return "?"


def log(line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    text = f"{stamp}  {line}"
    print(text, flush=True)
    try:
        os.makedirs(STATE, exist_ok=True)
        with open(LOG, "a") as handle:
            handle.write(text + "\n")
    except OSError:
        pass


seen = settings_pids()
log(f"--- watcher started (already running: {len(seen)}), sink={sink()} ---")

while True:
    now = settings_pids()
    for pid in now - seen:
        cmd = cmdline_of(pid) or "?"
        parent = ppid_of(pid)
        parent_cmd = cmdline_of(parent) if parent else None
        log(f"SETTINGS pid={pid} cmd={cmd[:120]}")
        log(f"         parent pid={parent} cmd={(parent_cmd or '?')[:120]}")
        log(f"         sink={sink()}")
    for pid in seen - now:
        log(f"settings exited pid={pid}")
    seen = now
    time.sleep(POLL)
