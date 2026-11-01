#!/usr/bin/env bash
# Toggle the default microphone between muted and unmuted.
# Bound to the pad's key 1 via a GNOME custom shortcut (ctrl-alt-shift-m).
set -euo pipefail

if ! command -v pactl >/dev/null; then
    echo "pactl not found" >&2
    exit 1
fi

if pactl get-source-mute @DEFAULT_SOURCE@ 2>/dev/null | grep -q 'yes'; then
    pactl set-source-mute @DEFAULT_SOURCE@ 0
    msg="Microphone unmuted"
else
    pactl set-source-mute @DEFAULT_SOURCE@ 1
    msg="Microphone muted"
fi

# Best-effort visual feedback; harmless if notify-send is absent.
command -v notify-send >/dev/null && notify-send -t 1200 -a "Macro pad" "${msg}" || true
